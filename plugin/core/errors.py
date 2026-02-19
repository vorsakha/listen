from __future__ import annotations


class MusicListenError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class DiscoveryError(MusicListenError):
    pass


class RetrievalError(MusicListenError):
    pass


class AnalysisError(MusicListenError):
    pass


class DescriptorError(MusicListenError):
    pass
