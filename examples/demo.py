"""Small demonstration input."""


def build_message(user: str) -> str:
    greeting = "Merhaba"
    timeout = 30
    message = f"{greeting}, {user}! timeout={timeout}"
    return message


print(build_message("Ada"))
