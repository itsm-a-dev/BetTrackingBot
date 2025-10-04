# Later: replace with proper DB ORM (SQLAlchemy)
bets = []

def add_bet(user_id, parsed_slip):
    bets.append({"user": user_id, "slip": parsed_slip})

def list_bets(user_id):
    return [b for b in bets if b["user"] == user_id]
