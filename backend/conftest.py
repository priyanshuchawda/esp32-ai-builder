import sys
from unittest.mock import MagicMock


def _passthrough_decorator(*args, **kwargs):
    if args and callable(args[0]) and len(args) == 1 and not kwargs:
        return args[0]
    return lambda func: func


def _columns(spec):
    count = spec if isinstance(spec, int) else len(spec)
    columns = [MagicMock() for _ in range(count)]
    for column in columns:
        column.button.return_value = False
    return columns


def _headless_streamlit():
    streamlit = MagicMock(name="headless_streamlit")
    streamlit.cache_resource.side_effect = _passthrough_decorator
    streamlit.fragment.side_effect = _passthrough_decorator
    streamlit.columns.side_effect = _columns
    streamlit.sidebar.columns.side_effect = _columns
    streamlit.sidebar.selectbox.return_value = "Signal Simulator"
    streamlit.sidebar.slider.side_effect = lambda *args, value=None, **kwargs: value
    streamlit.sidebar.number_input.side_effect = lambda *args, value=None, **kwargs: value
    streamlit.sidebar.button.return_value = False
    streamlit.selectbox.return_value = "Auto Cycle"
    return streamlit


# Unit tests target sensing and display helper behavior, not Streamlit runtime setup.
sys.modules["streamlit"] = _headless_streamlit()
