def init_chatbot(app):
    """Gắn chatbot vào app: đúng 1 dòng trong app.py -- `init_chatbot(app)`.
    Gỡ dòng này (và thẻ <script> trong base.html) là rollback hoàn toàn."""
    from dotenv import load_dotenv

    from event_checkin.chatbot.rate_limit import limiter
    from event_checkin.controllers.chat_controller import chat_bp

    load_dotenv()  # không ghi đè biến môi trường đã có
    limiter.init_app(app)
    app.register_blueprint(chat_bp)
