import os

from app import app as application

if __name__ == "__main__":
    from waitress import serve

    # Default (4 threads) is far too low for a public check-in page hit by
    # hundreds of people around the same time -- each request only holds a
    # thread for the duration of a few fast, indexed DB queries (certificate
    # rendering and email are no longer part of check-in at all -- admins send
    # them later in a background batch, see certificates/mailer.py), so a
    # larger thread count is safe here.
    serve(application, listen="127.0.0.1:8000", threads=int(os.getenv("WAITRESS_THREADS", "32")))
