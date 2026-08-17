from app import app as application

if __name__ == "__main__":
    from waitress import serve

    serve(application, listen="127.0.0.1:8000")
