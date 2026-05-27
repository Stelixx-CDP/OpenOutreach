# tests/browser/test_withdraw.py
from unittest.mock import patch

import pytest

from linkedin.actions.withdraw import withdraw_old_invitations


@pytest.mark.django_db
def test_withdraw_action_with_mock_html(page, fake_session):
    html_content = """
    <ul class="invitation-list">
        <li class="invitation-card" id="card-1">
            <span class="name">Lead 1</span>
            <span class="time">Sent 1 week ago</span>
            <button class="withdraw-btn" onclick="this.closest('li').remove()">Withdraw</button>
        </li>
        <li class="invitation-card" id="card-2">
            <span class="name">Lead 2</span>
            <span class="time">Sent 3 weeks ago</span>
            <button class="withdraw-btn" onclick="this.closest('li').remove()">Withdraw</button>
        </li>
        <li class="invitation-card" id="card-3">
            <span class="name">Lead 3</span>
            <span class="time">Sent 1 month ago</span>
            <button class="withdraw-btn" onclick="this.closest('li').remove()">Withdraw</button>
        </li>
        <li class="invitation-card" id="card-4">
            <span class="name">Lead 4</span>
            <span class="time">Sent 2 days ago</span>
            <button class="withdraw-btn" onclick="this.closest('li').remove()">Withdraw</button>
        </li>
    </ul>
    """
    page.set_content(html_content)
    
    # Mock fake_session with our Playwright page
    fake_session.page = page
    fake_session.wait = lambda: None
    
    # Run the withdraw process
    # Mock page.goto to not navigate to actual URL
    with patch.object(page, "goto") as mock_goto:
        withdrawn = withdraw_old_invitations(fake_session)
        mock_goto.assert_called_once_with("https://www.linkedin.com/mynetwork/invitation-manager/sent/")
        
    assert withdrawn == 2
    
    # Check that card-2 and card-3 were removed, but card-1 and card-4 remain
    assert page.locator("#card-1").count() == 1
    assert page.locator("#card-2").count() == 0
    assert page.locator("#card-3").count() == 0
    assert page.locator("#card-4").count() == 1
