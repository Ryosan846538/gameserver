import uuid
from enum import IntEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.exc import NoResultFound

from .db import engine


class InvalidToken(Exception):
    """指定されたtokenが不正だったときに投げるエラー"""


# サーバーで生成するオブジェクトは strict を使う
class SafeUser(BaseModel, strict=True):
    """token を含まないUser"""

    id: int
    name: str
    leader_card_id: int


def create_user(name: str, leader_card_id: int) -> str:
    """Create new user and returns their token"""
    # UUID4は天文学的な確率だけど衝突する確率があるので、気にするならリトライする必要がある。
    # サーバーでリトライしない場合は、クライアントかユーザー（手動）にリトライさせることになる。
    # ユーザーによるリトライは一般的には良くないけれども、確率が非常に低ければ許容できる場合もある。
    token = str(uuid.uuid4())
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO `user` (name, token, leader_card_id)"
                " VALUES (:name, :token, :leader_card_id)"
            ),
            {"name": name, "token": token, "leader_card_id": leader_card_id},
        )
        print(f"create_user(): {result.lastrowid=}")  # DB側で生成されたPRIMARY KEYを参照できる
    return token


def _get_user_by_token(conn, token: str) -> SafeUser | None:
    # TODO: 実装(わからなかったら資料を見ながら)
    result = conn.execute(
        text("SELECT `id`, `name`, `leader_card_id` FROM `user` WHERE `token`=:token"),
        {"token": token},
    )
    try:
        row = result.one()
    except NoResultFound:
        return None
    return SafeUser.model_validate(row, from_attributes=True)


def get_user_by_token(token: str) -> SafeUser | None:
    with engine.begin() as conn:
        return _get_user_by_token(conn, token)


def update_user(token: str, name: str, leader_card_id: int) -> None:
    with engine.begin() as conn:
        # TODO: 実装
        result = conn.execute(
            text(
                "UPDATE `user` SET `name`=:name, `leader_card_id`=:leader_card_id WHERE `token`=:token"
            ),
            {"name": name, "leader_card_id": leader_card_id, "token": token},
        )

        if result.rowcount == 0:
            raise InvalidToken("No user found with the provided token.")


# IntEnum の使い方の例
class LiveDifficulty(IntEnum):
    """難易度"""

    normal = 1
    hard = 2


class JoinRoomResult(IntEnum):
    Ok = 1
    RoomFull = 2
    Disbanded = 3
    OtherError = 4


class WaitRoomStatus(IntEnum):
    Waiting = 1
    LiveStart = 2
    Dissolution = 3


class RoomInfo(BaseModel):
    room_id: int
    live_id: int
    joined_user_count: int
    max_user_count: int


class RoomUser(BaseModel):
    user_id: int
    name: str
    leader_card_id: int
    select_diffuculty: LiveDifficulty
    is_me: bool
    is_host: bool


def create_room(token: str, live_id: int, difficulty: LiveDifficulty):
    """部屋を作ってroom_idを返します"""
    with engine.begin() as conn:
        user = _get_user_by_token(conn, token)
        if user is None:
            raise InvalidToken
        # TODO: 実装
        result = conn.execute(
            text(
                "INSERT INTO `room` (live_id, joined_user_count, max_user_count)"
                " VALUES (:live_id, 1, 4)"
            ),
            {"live_id": live_id},
        )
        room_id = result.lastrowid
        print(f"create_room(): {room_id=}")
        _insert_room_member(conn, room_id, user.id, difficulty.value)
        return room_id


def _insert_room_member(conn, room_id: int, user_id: int, difficulty: int):
    conn.execute(
        text(
            "INSERT INTO `room_member` (room_id, user_id, difficulty)"
            " VALUES (:room_id, :user_id, :difficulty)"
        ),
        {"room_id": room_id, "user_id": user_id, "difficulty": difficulty}
    )


def list_room(live_id: int):
    with engine.begin() as conn:
        if live_id == 0:
            result = conn.execute(
                text(
                    "SELECT room_id, live_id, joined_user_count, max_user_count FROM `room`"
                )
            )
        else:
            result = conn.execute(
                text(
                    "SELECT room_id, live_id, joined_user_count, max_user_count FROM `room` WHERE live_id = :live_id"
                ),
                {"live_id": live_id}
            )
        room_list = []
        for row in result:
            room_info = RoomInfo(
                room_id=row._mapping["room_id"],
                live_id=row._mapping["live_id"],
                joined_user_count=row._mapping["joined_user_count"],
                max_user_count=row._mapping["max_user_count"]
            )
            room_list.append(room_info)
    return room_list


def join_room(room_id: int, select_difficulty: LiveDifficulty) -> JoinRoomResult:
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "SELECT room_id, joined_user_count, max_user_count FROM `room` WHERE room_id = :room_id"
            ),
            {"room_id": room_id}
        )
        room = result.one()

        if not room:
            print(f"create_room(): {JoinRoomResult.Disbanded}")
            return JoinRoomResult.Disbanded

        if room._mapping["joined_user_count"] >= room._mapping["max_user_count"]:
            return JoinRoomResult.RoomFull

        conn.execute(
            text(
                "UPDATE `room` SET joined_user_count = joined_user_count + 1 WHERE room_id= :room_id"
                ),
            {"room_id": room_id}
        )
    return JoinRoomResult.Ok
