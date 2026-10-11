from __future__ import annotations

import django.dispatch


shelved = django.dispatch.Signal()
unshelved = django.dispatch.Signal()
