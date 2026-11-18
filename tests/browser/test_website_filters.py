"""Browser smoke test. Requires Playwright, Chromium and a running Frappe site.

WAKAMARIA_TEST_URL=http://wakamaria-test.localhost:18080/wakamaria python tests/browser/test_website_filters.py
Uses mocked match-list responses; no production records are modified.
"""
import json
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get('WAKAMARIA_TEST_URL', 'http://wakamaria-test.localhost:18080/wakamaria')
league = {'name': 'L1', 'league_name': 'Test League', 'country': 'Test', 'league_image': None}
def row(name, kickoff, confirmed):
    return {'name': name, 'league': 'L1', 'home_team': name, 'away_team': 'Visitors', 'kickoff': kickoff,
            'prediction': '12', 'result_confirmed': confirmed, 'home_score': 1, 'away_score': 0,
            'outcome': 'Win' if confirmed else 'Pending', 'provider_status': ''}

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), args=['--no-sandbox'])
    for width in (1280, 375, 320):
        page = browser.new_page(viewport={'width': width, 'height': 900})
        page.clock.install()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        items = [row('Future', '2099-01-01 12:00:00', 0), row('Past Pending', '2000-01-01 12:00:00', 0), row('Final', '2000-01-02 12:00:00', 1)]
        def match_list(route):
            route.fulfill(status=200, content_type='application/json', body=json.dumps({'message': {'leagues': [league], 'matches': items, 'timezone': 'Africa/Dar_es_Salaam'}}))
        page.route('**/api/method/wakamaria.api.list_matches', match_list)
        response=page.goto(URL, wait_until='networkidle')
        assert response.status==200
        page.locator('.match-row').first.wait_for()
        assert page.locator('.match-row').count() == 2
        assert 'Future' in page.locator('#match-list').inner_text() and 'Past Pending' in page.locator('#match-list').inner_text()
        assert 'Final' not in page.locator('#match-list').inner_text()
        assert page.locator('#all-count').inner_text() == '2'
        page.locator('[data-status="upcoming"]').click()
        assert page.locator('.match-row').count() == 1 and 'Future' in page.locator('#match-list').inner_text()
        page.locator('[data-status="finished"]').click()
        assert page.locator('.match-row').count() == 1 and 'Final' in page.locator('#match-list').inner_text()
        page.locator('[data-status="all"]').click()
        # The server confirms Future; background polling should move it without a page reload.
        items[0] = row('Future', '2099-01-01 12:00:00', 1)
        with page.expect_response('**/api/method/wakamaria.api.list_matches'):
            page.clock.fast_forward(60000)
        page.wait_for_function("!document.querySelector('#match-list').textContent.includes('Future')")
        assert page.locator('.match-row').count() == 1
        page.locator('[data-status="finished"]').click()
        assert page.locator('.match-row').count() == 2 and 'Future' in page.locator('#match-list').inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
        assert not errors, errors
        print(f'{width}px: current/upcoming/finished, counts and automatic refresh passed')
        page.close()
    browser.close()
