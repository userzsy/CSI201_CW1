"""Own room state, quiz rules and deadlines for the server event loop.

Only the selectors event loop mutates this data.

CONNECTED -> AUTHENTICATED is managed by SessionRegistry. Room membership
adds LOBBY -> QUESTION_OPEN -> QUESTION_CLOSED -> ... -> FINISHED.
Leaving returns a session to AUTHENTICATED. QUESTION_CLOSED is the atomic
result-publication transition; the next question opens without a sleep.
"""


# Imports

from dataclasses import dataclass, field
from enum import StrEnum
import time

from .protocol import ApplicationError, ErrorCode as E, MessageType as M
from .quiz_loader import public_quizzes


# Game States

class GameState(StrEnum):
    CONNECTED = "CONNECTED"
    AUTHENTICATED = "AUTHENTICATED"
    LOBBY = "LOBBY"
    QUESTION_OPEN = "QUESTION_OPEN"
    QUESTION_CLOSED = "QUESTION_CLOSED"
    FINISHED = "FINISHED"


# Player, Room and Leaderboard Data

@dataclass
class Player:
    session: object
    ready: bool = False
    active: bool = True
    score: int = 0
    correct_answers: int = 0


@dataclass
class Room:
    room_code: str
    quiz: dict
    host_id: str
    players: dict = field(default_factory=dict)
    state: GameState = GameState.LOBBY
    question_index: int = -1
    deadline: float | None = None
    answers: dict = field(default_factory=dict)
    closed_questions: set = field(default_factory=set)

    def active_players(self):
        return [p for p in self.players.values() if p.active]

    def player_list(self):
        return [{"user_id": p.session.user_id, "name": p.session.name,
                 "ready": p.ready, "is_host": p.session.user_id == self.host_id}
                for p in self.active_players()]

    def leaderboard(self):
        ordered = sorted(self.players.values(),
                         key=lambda p: (-p.score, -p.correct_answers, p.session.user_id))
        return [{"rank": i, "user_id": p.session.user_id, "name": p.session.name,
                 "score": p.score, "correct_answers": p.correct_answers}
                for i, p in enumerate(ordered, 1)]

    def listing_view(self):
        return {"room_code": self.room_code, "quiz_id": self.quiz["quiz_id"],
                "title": self.quiz["title"], "host_id": self.host_id,
                "player_count": len(self.active_players()), "capacity": 10,
                "state": str(self.state)}

    def view(self):
        return {**self.listing_view(), "players": self.player_list()}


# Quiz Engine and Question Publication

class QuizEngine:
    def __init__(self, room, emit, clock=time.monotonic):
        self.room, self.emit, self.clock = room, emit, clock

    def broadcast(self, kind, payload):
        for player in list(self.room.active_players()):
            self.emit(player.session, kind, payload)

    def start(self):
        room = self.room
        self.broadcast(M.QUIZ_STARTED_EVENT,
                       {"quiz_id": room.quiz["quiz_id"], "title": room.quiz["title"],
                        "total_questions": len(room.quiz["questions"])})
        self._next_question()

    def _next_question(self):
        room = self.room
        room.question_index += 1
        room.answers = {}
        question = room.quiz["questions"][room.question_index]
        room.state = GameState.QUESTION_OPEN
        # This room owns its deadline; the server loop checks it without timer threads.
        room.deadline = self.clock() + question["time_limit"]
        # Explicit allowlist: answer and extra bank members never enter this event.
        payload = {key: question[key] for key in
                   ("question_id", "text", "options", "time_limit", "points")}
        payload["number"] = room.question_index + 1
        self.broadcast(M.QUESTION_EVENT, payload)

    # Answer Validation and Acceptance

    def answer(self, session, question_id, answer):
        room = self.room
        if not isinstance(question_id, str) or not isinstance(answer, str) or answer not in ("A", "B", "C", "D"):
            raise ApplicationError(E.INVALID_ANSWER, "Require question_id and answer A, B, C or D")
        if question_id in room.closed_questions:
            raise ApplicationError(E.QUESTION_CLOSED, "This question has closed")
        if room.state != GameState.QUESTION_OPEN or self.clock() >= room.deadline:
            raise ApplicationError(E.QUESTION_CLOSED, "The current question is closed")
        if question_id != room.quiz["questions"][room.question_index]["question_id"]:
            raise ApplicationError(E.INVALID_ANSWER, "Question ID does not match the current question")
        if session.user_id in room.answers:
            raise ApplicationError(E.DUPLICATE_ANSWER, "An answer has already been accepted")
        room.answers[session.user_id] = answer
        return {"accepted": True, "question_id": question_id}

    # Deadlines, Scoring and Results

    def tick(self):
        room = self.room
        if room.state != GameState.QUESTION_OPEN:
            return
        active = room.active_players()
        if self.clock() < room.deadline and not all(p.session.user_id in room.answers for p in active):
            return
        self._close_question()

    def _close_question(self):
        room = self.room
        question = room.quiz["questions"][room.question_index]
        room.state = GameState.QUESTION_CLOSED
        room.closed_questions.add(question["question_id"])
        room.deadline = None
        awards = {}
        for user_id, player in room.players.items():
            correct = room.answers.get(user_id) == question["answer"]
            awards[user_id] = question["points"] if correct else 0
            player.score += awards[user_id]
            player.correct_answers += int(correct)
        leaderboard = room.leaderboard()
        for player in list(room.active_players()):
            user_id = player.session.user_id
            self.emit(player.session, M.QUESTION_RESULT_EVENT,
                      {"question_id": question["question_id"],
                       "correct_answer": question["answer"],
                       "your_answer": room.answers.get(user_id),
                       "points_awarded": awards[user_id], "leaderboard": leaderboard})
        if room.question_index + 1 == len(room.quiz["questions"]):
            room.state = GameState.FINISHED
            self.broadcast(M.QUIZ_FINISHED_EVENT,
                           {"quiz_id": room.quiz["quiz_id"], "final_leaderboard": leaderboard,
                            "winner": leaderboard[0] if leaderboard else None})
        else:
            self._next_question()


# Room Registry and Public Listings

class RoomManager:
    def __init__(self, bank, emit, clock=time.monotonic):
        self.bank, self.emit, self.clock = bank, emit, clock
        self.quizzes = {q["quiz_id"]: q for q in bank["quizzes"]}
        self.rooms = {}
        self.engines = {}
        self._sequence = 0

    def list_quizzes(self):
        return public_quizzes(self.bank)

    def list_rooms(self, cursor=None):
        if cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 128):
            raise ApplicationError(E.INVALID_MESSAGE, "cursor must be null or a 1-128 character string")
        return [room.listing_view() for code, room in sorted(self.rooms.items())
                if (cursor is None or code > cursor)
                and room.state == GameState.LOBBY and len(room.active_players()) < 10]

    # Room Creation and Membership

    def _unattached(self, session):
        if session.room_code is not None:
            raise ApplicationError(E.ALREADY_IN_ROOM, "Leave the current room first")

    def _attach(self, room, session):
        room.players[session.user_id] = Player(session)
        session.room_code = room.room_code

    def create(self, session, quiz_id):
        self._unattached(session)
        if not isinstance(quiz_id, str):
            raise ApplicationError(E.INVALID_MESSAGE, "quiz_id must be a string")
        if quiz_id not in self.quizzes:
            raise ApplicationError(E.QUIZ_NOT_FOUND, "Quiz does not exist")
        self._sequence += 1
        code = f"R{self._sequence:06d}"
        room = Room(code, self.quizzes[quiz_id], session.user_id)
        self.rooms[code] = room
        self.engines[code] = QuizEngine(room, self.emit, self.clock)
        self._attach(room, session)
        return room

    def join(self, session, room_code):
        self._unattached(session)
        if not isinstance(room_code, str) or room_code not in self.rooms:
            raise ApplicationError(E.ROOM_NOT_FOUND, "Room does not exist")
        room = self.rooms[room_code]
        if room.state != GameState.LOBBY:
            raise ApplicationError(E.INVALID_STATE, "Room has already started")
        if len(room.players) >= 10:
            raise ApplicationError(E.ROOM_FULL, "Room has reached ten players")
        self._attach(room, session)
        return room

    def current(self, session):
        room = self.rooms.get(session.room_code)
        if room is None or session.user_id not in room.players or not room.players[session.user_id].active:
            raise ApplicationError(E.NOT_IN_ROOM, "You do not belong to a room")
        return room

    # Player Status, Readiness and Start

    def status(self, room, extra_recipients=()):
        payload = {"room_code": room.room_code, "players": room.player_list(),
                   "host_id": room.host_id}
        recipients = [p.session for p in room.active_players()] + list(extra_recipients)
        for session in recipients:
            self.emit(session, M.PLAYER_STATUS_EVENT, payload)

    def ready(self, session, ready):
        room = self.current(session)
        if type(ready) is not bool:
            raise ApplicationError(E.INVALID_MESSAGE, "ready must be a boolean")
        if room.state != GameState.LOBBY:
            raise ApplicationError(E.INVALID_STATE, "Readiness can only change in the lobby")
        room.players[session.user_id].ready = ready
        self.status(room)

    def start(self, session):
        room = self.current(session)
        if session.user_id != room.host_id:
            raise ApplicationError(E.NOT_ROOM_HOST, "Only the host may start")
        if room.state != GameState.LOBBY:
            raise ApplicationError(E.INVALID_STATE, "Room is not in the lobby")
        if len(room.players) < 2 or not all(p.ready for p in room.players.values()):
            raise ApplicationError(E.PLAYERS_NOT_READY, "At least two players, all ready, are required")
        self.engines[room.room_code].start()

    # Room Departure and Closure

    def leave(self, session):
        room = self.rooms.get(session.room_code)
        if room is None:
            session.room_code = None
            return
        player = room.players.get(session.user_id)
        if player is None or not player.active:
            session.room_code = None
            return
        session.room_code = None
        if room.state == GameState.LOBBY:
            del room.players[session.user_id]
            if room.host_id == session.user_id and room.players:
                room.host_id = next(iter(room.players))
        else:
            # Retain score and any accepted answer.
            player.active = False
        if not room.active_players():
            self.emit(session, M.ROOM_CLOSED_EVENT,
                      {"room_code": room.room_code, "reason": "No active players remain"})
            del self.rooms[room.room_code]
            del self.engines[room.room_code]
        else:
            # Leaver also receives an event acknowledging successful departure.
            self.status(room, (session,))

    # Engine Dispatch and Resource Cleanup

    def answer(self, session, question_id, answer):
        room = self.current(session)
        return self.engines[room.room_code].answer(session, question_id, answer)

    def tick(self):
        # Check each room independently; answers, scores and deadlines stay with its engine.
        for engine in list(self.engines.values()):
            engine.tick()

    def next_timeout(self):
        deadlines = [r.deadline for r in self.rooms.values() if r.deadline is not None]
        return max(0.0, min(0.1, min(deadlines) - self.clock())) if deadlines else 0.1

    def clear(self):
        for room in self.rooms.values():
            for player in room.players.values():
                player.session.room_code = None
        self.rooms.clear()
        self.engines.clear()
