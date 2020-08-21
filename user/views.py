from flask import Blueprint, render_template, request, redirect, session, url_for, abort
import bcrypt
import uuid
import os
from werkzeug import secure_filename
from mongoengine import Q
from datetime import datetime, date

from user.models import User
from user.forms import RegisterForm, LoginForm, EditForm, ForgotForm, PasswordResetForm
from utilities.common import email
from settings import UPLOAD_FOLDER
from utilities.imaging import thumbnail_process
from utilities.maxxSec import maxx_encode
from relationship.models import Relationship
from user.decorators import login_required
from feed.forms import FeedPostForm
from feed.models import Message

user_app = Blueprint('user_app', __name__)

@user_app.route('/register', methods=('GET', 'POST'))
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        # salt = bcrypt.gensalt()
        # hashed_password = bcrypt.hashpw(form.password.data, salt)
        code = str(uuid.uuid4())
        password64 = maxx_encode(form.password.data)
        user = User(
            username=form.username.data,
            password=password64,
            email=form.email.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            change_configuration={
                "new_email": form.email.data.lower(),
                "confirmation_code": code
            }
        )

        # email the user
        body_html = render_template('mail/user/register.html', user=user)
        body_text = render_template('mail/user/register.txt', user=user)
        email(user.email, "Welcome to White History Week", body_html, body_text)

        user.save()
        return redirect(url_for('home_app.home'))
    return render_template('user/register.html', form=form)


@user_app.route('/login', methods=('GET', 'POST'))
def login():
    form = LoginForm()
    error = None
    if request.method == 'GET' and request.args.get('next'):
        session['next'] = request.args.get('next')
    if form.validate_on_submit():
        user = User.objects.filter(
            username=form.username.data
        ).first()
        if user:
            pw_in = form.password.data
            pw_check = maxx_encode(pw_in)
            if user.password == pw_check:
#            if bcrypt.hashpw(form.password.data, user.password) == user.password:
                session['username'] = form.username.data
                if 'next' in session:
                    next = session.get('next')
                    session.pop('next')
                    return redirect(next)
                else:
                    return redirect(url_for('home_app.home'))
#                    return "<h3 style='color:#CB4154'>Successful login</h3><h4 >Waiting to implement 'home_app.home'</h4>"
            else:
                user = None
        if not user:
            error = 'Incorrect credentials'
    return render_template('user/login.html', form=form, error=error)


@user_app.route('/logout')
def logout():
    if session.get('username'):
        session.pop('username')
    return redirect(url_for('user_app.login'))


@user_app.route('/<username>/friends/<int:friends_page_number>', endpoint='profile-friends-page')
@user_app.route('/<username>/friends', endpoint='profile-friends')
@user_app.route('/<username>')
def profile(username, friends_page_number=1):
    logged_user = None
    edit_profile = False
    rel = None
    friends_page = False
    user = User.objects.filter(username=username).first()

    if user:
        if session.get('username'):
            logged_user = User.objects.filter(username=session.get('username')).first()
            rel = Relationship.get_relationship(logged_user, user)

        if session.get('username') and user.username == session.get('username'):
            edit_profile = True

        # get friends
        friends = Relationship.objects.filter(
            from_user=user,
            rel_type=Relationship.FRIENDS,
            status=Relationship.APPROVED
        )
        friends_total = friends.count()

        if 'friends' in request.url:
            friends_page = True
            friends = friends.paginate(page=friends_page_number, per_page=3)
        else:
            friends = friends[:5]
        form = FeedPostForm()

        # get user messages
        profile_messages = Message.objects.filter(
            Q(from_user=user) | Q(to_user=user)).order_by('-create_date')[:10]

        return render_template('user/profile.html',
                               user=user,
                               logged_user=logged_user,
                               rel=rel,
                               edit_profile=edit_profile,
                               friends=friends,
                               friends_total=friends_total,
                               friends_page=friends_page,
                               form=form,
                               profile_messages=profile_messages,
                               images=None
                               )
    else:
        abort(404)


@user_app.route('/edit', methods=('GET', 'POST'))
@login_required
def edit():
    error = None
    message = None
    user = User.objects.filter(username=session.get('username')).first()
    if user:
        form = EditForm(obj=user)
        if form.validate_on_submit():
            # check if image
            image_ts = None
            if request.files.get('image'):
                filename = secure_filename(form.image.data.filename)
                file_path = os.path.join(UPLOAD_FOLDER, 'user', filename)
                form.image.data.save(file_path)
                image_ts = str(thumbnail_process(file_path, 'user', str(user.id)))
            if user.username != form.username.data.lower():
                if User.objects.filter(username=form.username.data.lower()).first():
                    error = "Username already exists"
                else:
                    session['username'] = form.username.data.lower()
                    form.username.data = form.username.data.lower()
            if user.email != form.email.data.lower():
                if User.objects.filter(email=form.email.data.lower()).first():
                    error = "Email already exists"
                else:
                    code = str(uuid.uuid4())

                    user.change_configuration = {
                        "new_email": form.email.data.lower(),
                        "confirmation_code": code
                    }
                    user.email_confirmed = False
                    form.email.data = user.email
                    message = "You will need to confirm the new email to complete this change"

                    # email the user
                    body_html = render_template('mail/user/change_email.html', user=user)
                    body_text = render_template('mail/user/change_email.txt', user=user)
                    email(user.change_configuration['new_email'], "Confirm your new email", body_html, body_text)

            if not error:
                form.populate_obj(user)
                if image_ts:
                    user.profile_image = image_ts
                user.save()
                if not message:
                    message = "Profile updated"

        return render_template("user/edit.html", form=form, error=error, message=message, user=user)
    else:
        abort(404)


@user_app.route('/confirm/<username>/<code>', methods=('GET', 'POST'))
def confirm(username, code):
    user = User.objects.filter(username=username).first()
    if user and user.change_configuration and user.change_configuration.get('confirmation_code'):
        if code == user.change_configuration.get('confirmation_code'):
            user.email = user.change_configuration.get('new_email')
            user.change_configuration = {}
            user.email_confirmed = True
            user.save()
            return render_template('user/email_confirmed.html')
    else:
        abort(404)


@user_app.route('/forgot', methods=('GET', 'POST'))
def forgot():
    error = None
    message = None
    form = ForgotForm()
    if form.validate_on_submit():
        user = User.objects.filter(email=form.email.data.lower()).first()
        if user:
            code = str(uuid.uuid4())
            user.change_configuration = {
                "password_reset_code": code
            }
            user.save()

            # email the user
            body_html = render_template('mail/user/password_reset.html', user=user)
            body_text = render_template('mail/user/password_reset.txt', user=user)
            email(user.email, "Password reset request", body_html, body_text)

        message = "You will receive a password reset email if we find that email in our system"
    return render_template('user/forgot.html', form=form, error=error, message=message)


@user_app.route('/password_reset/<username>/<code>', methods=('GET', 'POST'))
def password_reset(username, code):
    message = None
    require_current = None

    form = PasswordResetForm()

    user = User.objects.filter(username=username).first()
    if not user or code != user.change_configuration.get('password_reset_code'):
        abort(404)

    if request.method == 'POST':
        del form.current_password
        if form.validate_on_submit():
            pw_in = form.password.data
            hashed_password = maxx_encode(pw_in)
            user.password = hashed_password
            # salt = bcrypt.gensalt()
            # hashed_password = bcrypt.hashpw(form.password.data, salt)
            # user.password = hashed_password
            user.change_configuration = {}
            user.save()

            if session.get('username'):
                session.pop('username')
            return redirect(url_for('user_app.password_reset_complete'))

    return render_template('user/password_reset.html',
                           form=form,
                           message=message,
                           require_current=require_current,
                           username=username,
                           code=code
                           )


@user_app.route('/password_reset_complete')
def password_reset_complete():
    return render_template('user/password_change_confirmed.html')


@user_app.route('/change_password', methods=('GET', 'POST'))
def change_password():
    require_current = True
    error = None
    form = PasswordResetForm()
    user = User.objects.filter(username=session.get('username')).first()
    if not user:
        abort(404)
    if request.method == 'POST':
        if form.validate_on_submit():
            current_pw_in = form.current_password.data
            pw_check = maxx_encode(current_pw_in)
            if user.password == pw_check:
                new_pw = maxx_encode(form.password.data)
                user.password = new_pw

                # if bcrypt.hashpw(form.current_password.data, user.password) == user.password:
            #     salt = bcrypt.gensalt()
            #     hashed_password = bcrypt.hashpw(form.password.data, salt)
            #     user.password = hashed_password
                user.save()
                # if user is logged in, log him out
                if session.get('username'):
                    session.pop('username')
                return redirect(url_for('user_app.password_reset_complete'))
            else:
                error = "Incorrect password"
    return render_template('user/password_reset.html',
                           form=form,
                           require_current=require_current,
                           error=error
                           )

@user_app.route("/user")
def user():
    user=User(bio='37', username='marian37', first_name='Marian', last_name='Anderson',
         email='marian37@maxxima.net', password='asdf')
    user.save()

    user=User(bio='38', username='mary38', first_name='Mary McLeod', last_name='Bethune',
         email='marym38@maxxima.net', password='asdf')
    user.save()

    users=User.objects.all()
    return render_template("user/user.html", users=users)


@user_app.route("/calendar")
def calendar():
    days = []
    day_one = date(2020,7,31)
    today = date.today()
    days_in = abs(today-day_one)
    days_in = days_in.days -1
    days_to_go = 180 - days_in
    _class= "got_it"         #default
    return render_template("user/calendar.html", days_in=days_in,_class=_class)


