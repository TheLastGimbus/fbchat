import attr
import datetime
from ._event_common import attrs_event, Event, UnknownEvent, ThreadEvent
from . import (
    _exception,
    _util,
    _user,
    _group,
    _thread,
    _client_payload,
    _delta_class,
    _delta_type,
)

from typing import Mapping


@attrs_event
class Typing(ThreadEvent):
    """Somebody started/stopped typing in a thread."""

    #: ``True`` if the user started typing, ``False`` if they stopped
    status = attr.ib(type=bool)

    @classmethod
    def _parse_orca(cls, session, data):
        author = _user.User(session=session, id=str(data["sender_fbid"]))
        status = data["state"] == 1
        return cls(author=author, thread=author, status=status)

    @classmethod
    def _parse(cls, session, data):
        # TODO: Rename this method
        author = _user.User(session=session, id=str(data["sender_fbid"]))
        thread = _group.Group(session=session, id=str(data["thread"]))
        status = data["state"] == 1
        return cls(author=author, thread=thread, status=status)


@attrs_event
class FriendRequest(Event):
    """Somebody sent a friend request."""

    #: The user that sent the request
    author = attr.ib(type=_user.User)

    @classmethod
    def _parse(cls, session, data):
        author = _user.User(session=session, id=str(data["from"]))
        return cls(author=author)


@attrs_event
class Presence(Event):
    """The list of active statuses was updated.

    Chat online presence update.
    """

    # TODO: Document this better!

    #: User ids mapped to their active status
    statuses = attr.ib(type=Mapping[str, _user.ActiveStatus])
    #: ``True`` if the list is fully updated and ``False`` if it's partially updated
    full = attr.ib(type=bool)

    @classmethod
    def _parse(cls, session, data):
        statuses = {
            str(d["u"]): _user.ActiveStatus._from_orca_presence(d) for d in data["list"]
        }
        return cls(statuses=statuses, full=data["list_type"] == "full")


def parse_delta(session, data):
    try:
        class_ = data.get("class")
        if class_ == "ClientPayload":
            yield from _client_payload.parse_client_payloads(session, data)
        elif class_ == "AdminTextMessage":
            yield _delta_type.parse_delta(session, data)
        else:
            event = _delta_class.parse_delta(session, data)
            if event:  # Skip `None`
                yield event
    except _exception.ParseError:
        raise
    except Exception as e:
        raise _exception.ParseError("Error parsing delta", data=data) from e


def parse_events(session, topic, data):
    # See Mqtt._configure_connect_options for information about these topics
    try:
        if topic == "/t_ms":
            if "deltas" not in data:
                return
            for delta in data["deltas"]:
                yield from parse_delta(session, delta)

        elif topic == "/thread_typing":
            yield Typing._parse(session, data)

        elif topic == "/orca_typing_notifications":
            yield Typing._parse_orca(session, data)

        elif topic == "/legacy_web":
            if data.get("type") == "jewel_requests_add":
                yield FriendRequest._parse(session, data)
            else:
                yield UnknownEvent(source="/legacy_web", data=data)

        elif topic == "/orca_presence":
            yield Presence._parse(session, data)

        else:
            yield UnknownEvent(source=topic, data=data)
    except _exception.ParseError:
        raise
    except Exception as e:
        raise _exception.ParseError(
            "Error parsing MQTT topic {}".format(topic), data=data
        ) from e
