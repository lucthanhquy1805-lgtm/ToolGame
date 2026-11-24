"""Panel base.

A panel owns one LabelFrame. load() copies account settings into widgets,
store() copies them back, apply_language() relabels everything in place.
"""


class Panel:
    def __init__(self, parent, tab):
        self.parent = parent
        self.tab = tab
        self.frame = None
        self.build()
        self.load()

    @property
    def account(self):
        return self.tab.account

    def t(self, translation_key, **kwargs):
        return self.tab.t(translation_key, **kwargs)

    def build(self):
        """Create widgets."""

    def load(self):
        """Account settings -> widgets."""

    def store(self):
        """Widgets -> account settings."""

    def apply_language(self):
        """Refresh every visible string."""

    def set_busy(self, running):
        """Disable editing while the session runs."""
