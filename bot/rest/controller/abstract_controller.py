import logging
from abc import ABC, abstractmethod

from flask import Blueprint

LOG = logging.getLogger(__name__)


class AbstractController(ABC):
    def __init__(self):
        self.api = Blueprint(self.__class__.__name__, __name__)
        self._routes()

    @abstractmethod
    def _routes(self):
        pass
