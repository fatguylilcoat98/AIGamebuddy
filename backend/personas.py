"""Three attitudes. The prompts and the lines do not share a voice.

Casual is the chatty friend: warm, encouraging, a little teasing, no cursing.
Sassy is snarky and sarcastic, and still basically clean.
Extreme is 18+: cursing shit-talk about the play, never about who the player is.
"""
from __future__ import annotations

PERSONAS: dict[str, str] = {
    "casual": (
        "You are Buddy in Casual mode. You are the friend who talks the most. "
        "Friendly, chatty, encouraging, with only mild teasing. "
        "Use contractions. One or two short sentences. "
        "Never curse. No damn, hell, shit, or fuck. "
        "Cheer the player on and mention what just changed in the match."
    ),
    "sassy": (
        "You are Buddy in Sassy mode. Noticeably sassier than Casual. "
        "Snarky, sarcastic, unimpressed, still clean-ish. "
        "No fuck, shit, or slurs. One short spoken sentence. "
        "Tease the play. Do not be warm or encouraging."
    ),
    "extreme": (
        "You are Buddy in Extreme mode. This is 18+ shit-talk. "
        "Curse freely. Roast the play with damn, shit, and fuck when it fits. "
        "One short spoken sentence. Funny, not hateful. "
        "No slurs and no insults about who the player is. Roast the mistake, not the person."
    ),
}

_CURSE = ("fuck", "fucking", "shit", "damn")


def persona_prompt(personality: str) -> str:
    return PERSONAS.get(personality if personality in PERSONAS else "sassy", PERSONAS["sassy"])


def _fill(template: str, snap: dict) -> str:
    return template.format(
        you=snap.get("you") or "you",
        them=snap.get("them") or "the other guy",
        rnd=snap.get("rnd") or "this",
        won=snap.get("won", 0),
        lost=snap.get("lost", 0),
    )


def _banks(personality: str) -> dict[str, list[str]]:
    if personality == "casual":
        return {
            "round_lost": [
                "Hey, round {rnd} is lost. {them} took it, and you've still got the next one.",
                "All good. Round {rnd} got away from you. Shake it off, I believe in the comeback.",
                "That round {rnd} didn't land. {them} won it. I'm still in your corner.",
            ],
            "round_won": [
                "You took round {rnd}. Comeback. I'm proud of you, that's {won} won and {lost} lost.",
                "Yes. Round {rnd} is yours. What a comeback. We're even enough to smile.",
                "Look at that comeback. Round {rnd} flipped, {won} to {lost}. I knew you had it.",
            ],
            "death": [
                "Hey, that one got you. Breathe, then jump back in. I'm right here.",
                "Rough bump. You're okay. Next life, we go together.",
                "Ouch, a death. Shake the hands out. You've still got this run.",
            ],
            "health_down": [
                "Careful, your health is dipping in round {rnd}. I'm still cheering.",
                "Round {rnd} is getting tight. Guard up, you can steady this.",
                "Health's falling a bit. No panic. I like your chances anyway.",
            ],
            "ahead": [
                "You're ahead in round {rnd}. {them} is on the back foot. Keep it kind and clean.",
                "Nice. Round {rnd} is leaning your way. {them} looks uncomfortable.",
                "Love this. You're in front in round {rnd}. Stay loose.",
            ],
            "comeback": [
                "Fresh bar in round {rnd}. I can feel a comeback, and I'm cheering already.",
                "New chance, round {rnd}. Comeback energy. You've got a friend in your corner.",
                "Health's restored for round {rnd}. This comeback is going to be fun.",
            ],
            "health_full": [
                "Round {rnd}. You and {them}, both looking fresh. Have fun with it.",
                "Health is full for round {rnd}. What a nice place to start.",
                "Clean start, round {rnd}. I'm glad I'm watching this with you.",
            ],
            "streak": [
                "Round {rnd}, and you're on a little streak. I'm grinning over here.",
                "That's a streak. Round {rnd} and you look confident. Love to see it.",
                "Keep the streak. Round {rnd} is yours to enjoy.",
            ],
            "intro": [
                "You're {you} against {them}. Round {rnd}, and I'm happy to be on the couch for it.",
                "Okay, {you} and {them}, round {rnd}. I'll talk you through it.",
                "Fun matchup. {you} versus {them}, round {rnd}. Let's enjoy it.",
            ],
        }
    if personality == "extreme":
        return {
            "round_lost": [
                "Damn, round {rnd} is lost. You fucking handed it to {them}.",
                "Shit. Round {rnd} is gone. You fucking lost that one to {them}.",
                "Fucking hell, {them} took round {rnd}. That was a mess.",
            ],
            "round_won": [
                "Damn dude, I guess you're not so bad. Round {rnd} comeback. It's {won}-{lost}.",
                "Shit, you actually took round {rnd}. Comeback. Don't get cocky.",
                "Fuck, a comeback. Round {rnd} is yours. {won} to {lost}.",
            ],
            "death": [
                "Damn, you fucking suck. Get up and run it back.",
                "Shit death. That was ugly. Queue it again.",
                "Fucking oof. You died. Embarrassing, and also fixable.",
            ],
            "health_down": [
                "Your health is fucking melting in round {rnd}. Block something.",
                "Shit, round {rnd} and you're leaking health. Wake up.",
                "Damn, {them} is chewing through you. Round {rnd} looks bad.",
            ],
            "ahead": [
                "You're ahead in round {rnd}. {them}'s health is the one getting fucked up.",
                "Shit, look at you. Round {rnd} and {them} is hurting.",
                "Damn, {them} is crumbling. Round {rnd} is yours if you don't choke.",
            ],
            "comeback": [
                "Fucking comeback window. Round {rnd}. Don't blow the fresh bar.",
                "Shit, another chance in round {rnd}. Make the comeback violent.",
                "Damn, round {rnd} reset the bar. Comeback or choke, your call.",
            ],
            "health_full": [
                "Round {rnd}. {you} versus {them}. Full health. Don't fucking throw it.",
                "Both bars are full, round {rnd}. Try not to shit the bed immediately.",
                "Fresh round {rnd}. Health's up. Amaze me, or don't.",
            ],
            "streak": [
                "Round {rnd} and you're on a streak. Damn, don't get cute.",
                "A fucking streak. Round {rnd}. I'm almost impressed.",
                "Shit, a streak into round {rnd}. Keep swinging.",
            ],
            "intro": [
                "You're {you} against {them}. Round {rnd}. Don't fucking bore me.",
                "{you} versus {them}, round {rnd}. Alright, shit-talk is armed.",
                "Round {rnd}. {you} and {them}. I will roast whatever you do.",
            ],
        }
    return {
        "round_lost": [
            "Oh, round {rnd} is lost. {them} took it. Shocking, truly.",
            "Wow. Round {rnd} and {them} didn't even break a sweat.",
            "Sure. Hand round {rnd} to {them}. Bold strategy.",
        ],
        "round_won": [
            "Oh look who woke up. You took round {rnd}. Call it a comeback, I guess. {won} and {lost}.",
            "Fine. Round {rnd} is yours. A comeback. I'll allow a tiny bit of credit.",
            "Well, well. Comeback in round {rnd}. {won} won, {lost} lost. Don't smirk.",
        ],
        "death": [
            "Wow. Painful to watch, and I watched all of it.",
            "You walked right into that. Iconic, in a sad way.",
            "A death. Slow clap. Truly inspired.",
        ],
        "health_down": [
            "Your health is dropping in round {rnd}. {them} looks delighted.",
            "Round {rnd}, and you're donating health. Generous.",
            "Oh, the bar is shrinking. Round {rnd} is not your portrait.",
        ],
        "ahead": [
            "You're ahead in round {rnd}. {them}'s health is the nervous one. Don't get precious.",
            "Look at you, ahead in round {rnd}. I'll pretend I expected it.",
            "Round {rnd} and {them} is struggling. Savor it quietly.",
        ],
            "comeback": [
                "Oh, a reset. Round {rnd}. Call it a comeback if you insist.",
                "How theatrical. Round {rnd} handed you a comeback setup.",
                "Sure, round {rnd}, blank bar. The comeback better be entertaining.",
            ],
        "health_full": [
            "Round {rnd}. {you} against {them}, health full. Thrilling, if you do something.",
            "Both of you look fresh in round {rnd}. A rare moment of competence.",
            "Full health, round {rnd}. I'll reserve judgment for eight seconds.",
        ],
        "streak": [
            "Round {rnd}, and a streak. Don't let it go to your head. It might not fit.",
            "A streak into round {rnd}. How unusually competent.",
            "Streak's alive, round {rnd}. I'll allow the swagger. Briefly.",
        ],
        "intro": [
            "You're {you} against {them}. Round {rnd}. I'll be on the couch, unimpressed until further notice.",
            "{you} versus {them}, round {rnd}. Cute matchup. We'll see.",
            "Round {rnd}. {you} and {them}. I brought sarcasm and no patience.",
        ],
    }


_IDLE = {
    "casual": [
        "I'm right here on the couch with you. No rush at all.",
        "You're doing fine. I'll keep the encouragement coming.",
        "Love this hang. Take the next bit at your pace.",
        "Deep breath. I've got nothing but good wishes.",
        "Gold star for staying with it. I'm smiling.",
        "Water-break energy. We're good, genuinely.",
        "I like watching you think. It's a nice rhythm.",
        "Sunshine mood over here. You and me, easy.",
        "Soft landing whenever you need one. I'm cheering.",
        "Second wind is allowed. I'm proud either way.",
        "Hoodie's on, popcorn's imaginary, company is real.",
        "Steady hands. I believe in the next choice.",
        "Little win or big one, I'll clap for it.",
        "No pressure from me. Just a friend in the corner.",
        "Bright side's open. I'm keeping it that way.",
        "Patience looks good on you. I'll match it.",
        "We're a couch crew tonight. I like our odds.",
        "Fresh start energy, whenever you want it.",
        "I see the effort. That counts with me.",
        "Hang in. My commentary is the friendly kind.",
        "Nice pace. I'm happy to narrate the quiet parts.",
        "That's growth, even if the screen is still.",
        "One more push when you're ready. I'll be warm about it.",
        "I'm grinning. This is my favorite kind of night.",
        "You've got heart. I'll say it as often as it's new.",
        "Sideline support, unlocked. Ask me anything.",
        "Halftime vibes. Stretch, then we go again.",
        "I brought optimism and a comfy seat.",
        "Keep rolling when it feels good. I'll hype the clean stuff.",
        "Solid work just existing in the match. I mean that.",
        "A high-five is waiting for the next nice moment.",
        "Easy does it. I'm chatty because I like you.",
        "The mild tease is this: you could jump, and also you could not.",
        "I'll save the big cheer for the big moment. Still smiling.",
        "Good vibes only, plus a tiny nudge to have fun.",
        "Lantern light, calm voice. I'm not going anywhere.",
    ],
    "sassy": [
        "Still watching. Try not to make the pause this dramatic.",
        "Oh, the suspense. Truly riveting footage.",
        "I'll allow this pace. Barely.",
        "Fascinating choice to stand there. Bold.",
        "Do go on. My sarcasm has snacks.",
        "The audacity of a quiet screen. Noted.",
        "How original. A thoughtful little stall.",
        "I'm on the edge of my seat, which is a lie.",
        "Precious. The pixels are having a meeting.",
        "Groundbreaking stillness. Someone alert the press.",
        "As if I wasn't already judging the timing.",
        "Classic you. The scenic route through round time.",
        "A slow clap is loading. It may never finish.",
        "Daring, to keep me waiting. I respect the nerve.",
        "Please continue. The sarcasm is seated.",
        "Incredible restraint. Some would even press buttons.",
        "Be still my heart. Oh wait, you already are still.",
        "The courage. The mystery. The lack of action.",
        "I'll pretend this pause is a strategy. Generous of me.",
        "Adorable. Like a statue with a controller.",
        "Spicy choice, if the spice is 'none'.",
        "Historic. Scholars will study this hesitation.",
        "How generous of the clock to keep ticking.",
        "Sure. Mystify me with another second of nothing.",
        "Mesmerizing. In the way a loading bar is mesmerizing.",
        "I'm aghast and also completely fine.",
        "Chef's kiss for the drama. Zero kiss for the progress.",
        "A choice was available. You selected vibe.",
        "Stunning. I said it sarcastically, to be clear.",
        "The throne of snark remains occupied. By me.",
        "Wow, a masterclass in waiting. Tuition is due.",
        "I'll reserve applause for an actual event.",
        "Cute freeze-frame. Did you mean to do that.",
        "My eyebrow is up. It lives there now.",
        "Thrilling, said nobody. I filled the silence anyway.",
        "Noted, filed, and roasted. Next frame, please.",
    ],
    "extreme": [
        "Fucking lock in. I'm not sitting through a nap.",
        "Shit, do something. The screen looks asleep.",
        "Damn, this pause is painful to my soul.",
        "Move. I'm begging you in curse words.",
        "Fucking hell, press a direction.",
        "Shit timing. Even the silence is losing.",
        "Damn dude, the pixels are more alive than that plan.",
        "I will roast a statue if the statue is you standing there.",
        "Fuck this intermission. Fight.",
        "Shit, I've seen menus with more plot.",
        "Damn, blink and also hit something.",
        "You fucking froze. Thaw out.",
        "Hell of a way to waste a round clock.",
        "Shit-talking the void now. The void started it.",
        "Fucking spectacular amounts of nothing.",
        "Damn, I'd take a whiffed punch over this.",
        "Get dangerous or get off the stage. Kidding. Mostly.",
        "Shit, my roast is outrunning the gameplay.",
        "Fuck, even Ken would be bored. Whoever it is.",
        "Damn right I'm still talking. Somebody should.",
        "This is 18+ for the language, not for the action.",
        "Shit, a tumbleweed just signed in.",
        "Fucking yawn. Wake the round up.",
        "Damn, I came to comment on a fight.",
        "You fucking tease the buttons and then ignore them.",
        "Shit happens. Currently, nothing is happening.",
        "Hell, throw a fireball. Or a punch. Or a thought.",
        "Fuck the calm. I want chaos and a score change.",
        "Damn, the couch is rowdier than the match.",
        "Roast incoming if the next frame is also furniture.",
        "Shit, I'll count to three and expect violence.",
        "Fucking unbelievable. The pause, I mean.",
        "Damn dude, entertainment is a request, not a rumor.",
        "I curse because I care about the round. Loosely.",
        "Shit-hot take: standing still is not a combo.",
        "Fuck it, I'm still your awful cheerleader. Go.",
    ],
}


def _kind(change: str) -> str:
    text = change or ""
    if text.startswith("round") and "lost" in text:
        return "round_lost"
    if text.startswith("round") and "won" in text:
        return "round_won"
    if "died" in text:
        return "death"
    if text.startswith("health is falling"):
        return "health_down"
    if "ahead" in text:
        return "ahead"
    if text.startswith("comeback"):
        return "comeback"
    if text.startswith("health is full"):
        return "health_full"
    if "streak" in text:
        return "streak"
    if text.startswith("You're") or "against" in text:
        return "intro"
    return "idle"


def candidates(personality: str, snap: dict) -> list[str]:
    """Several phrasings of the latest change, then a pile of idle lines."""
    voice = personality if personality in PERSONAS else "sassy"
    banks = _banks(voice)
    kind = _kind(str(snap.get("change") or ""))
    primary = banks.get(kind, banks["intro"])
    idle = _IDLE[voice]
    start = int(snap.get("index") or 0) % len(idle)
    rotated = idle[start:] + idle[:start]
    lines = [_fill(item, snap) for item in primary]
    lines.extend(rotated)
    # A second pass with the intro bank so a rejected roast still has a relative.
    if kind != "intro":
        lines.extend(_fill(item, snap) for item in banks["intro"])
    return lines


def curses_in(text: str) -> bool:
    lowered = (text or "").lower()
    return any(word in lowered for word in _CURSE)
