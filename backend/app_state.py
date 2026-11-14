"""Process-wide handle so the launcher, overlay, and HTTP API share one Buddy."""

SESSION = None
# Set by the overlay so a console-close handler can ask Tk to quit.
request_quit = None
# uvicorn.Server, so quit can stop the API thread.
api_server = None
