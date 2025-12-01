from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import List, Optional

from app.domain.messages import TurbineMessage


class QueueStrategy(Enum):
    """Strategy for selecting the next message from the queue."""

    FIFO = auto()  # First in, first out
    LIFO = auto()  # Last in, first out


@dataclass
class TurbineMessageQueue:
    """
    In-memory queue for TurbineMessage objects.

    Matches the UML TurbineMessageQueue:
    - maxSize
    - items
    - strategy
    - currentSize
    - droppedMessagesCount
    - lastEnqueueAt
    - lastDequeueAt
    """

    max_size: int = 1_000
    strategy: QueueStrategy = QueueStrategy.FIFO

    items: List[TurbineMessage] = field(default_factory=list)
    dropped_messages_count: int = 0

    last_enqueue_at: Optional[datetime] = None
    last_dequeue_at: Optional[datetime] = None

    @property
    def current_size(self) -> int:
        """Current number of messages in the queue."""
        return len(self.items)

    def is_empty(self) -> bool:
        """Return True if the queue is empty."""
        return not self.items

    def is_full(self) -> bool:
        """Return True if the queue has reached or exceeded its max size."""
        return self.current_size >= self.max_size

    def enqueue(self, message: TurbineMessage) -> None:
        """
        Add a message to the queue.

        If the queue is full, a message is dropped according to the strategy
        and dropped_messages_count is incremented.
        """
        self.last_enqueue_at = datetime.utcnow()

        if self.is_full():
            # Drop one message according to strategy
            if self.strategy is QueueStrategy.FIFO:
                # Drop the oldest (front of the queue)
                if self.items:
                    self.items.pop(0)
            else:  # LIFO
                # Drop the most recent (end of the queue)
                if self.items:
                    self.items.pop()

            self.dropped_messages_count += 1

        self.items.append(message)

    def _select_index_for_dequeue(self) -> Optional[int]:
        """Return the index of the next message to dequeue, or None if empty."""
        if not self.items:
            return None

        if self.strategy is QueueStrategy.FIFO:
            return 0
        else:  # LIFO
            return len(self.items) - 1

    def dequeue(self) -> Optional[TurbineMessage]:
        """
        Remove and return the next message according to the strategy.

        Returns None if the queue is empty.
        """
        index = self._select_index_for_dequeue()
        if index is None:
            return None

        self.last_dequeue_at = datetime.utcnow()
        return self.items.pop(index)

    def peek(self) -> Optional[TurbineMessage]:
        """
        Return the next message without removing it.

        Returns None if the queue is empty.
        """
        index = self._select_index_for_dequeue()
        if index is None:
            return None

        return self.items[index]

    def clear(self) -> None:
        """Remove all messages from the queue."""
        self.items.clear()
        self.last_dequeue_at = datetime.utcnow()

    def get_all_messages(self) -> List[TurbineMessage]:
        """
        Return a shallow copy of all messages currently in the queue.

        Useful for debugging or inspection.
        """
        return list(self.items)
