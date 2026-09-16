from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_dashboard_common_metrics_and_controls():
    app = Path(__file__).resolve().parents[1]/'app.py'
    at = AppTest.from_file(str(app), default_timeout=60).run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 12
    assert len(at.tabs) == 5
    at.number_input[0].set_value(.2)
    next(x for x in at.selectbox if x.label=='평가 기간').select('2020–2022 사이클')
    at.run()
    assert not at.exception
    at.radio[0].set_value('시작일 신규 투자').run()
    assert not at.exception
    at.multiselect[0].set_value([]).run()
    assert not at.exception
    assert any('한 개 이상' in x.value for x in at.info)
