from flask import Flask
from flask_mongoengine import MongoEngine
db = MongoEngine()

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('settings.py')
    db.init_app(app)

    from user.views import user_app
    app.register_blueprint(user_app)

    from relationship.views import relationship_app
    app.register_blueprint(relationship_app)

    from feed.views import feed_app
    app.register_blueprint(feed_app)

    from home.views import home_app
    app.register_blueprint(home_app)

    return app

