import unittest
from PIL import Image, ImageDraw
from wakamaria.card_ocr import detect_cards, parse_teams, parse_tip

class CardOCRTest(unittest.TestCase):
    def test_all_tips_and_reject_garbage(self):
        for value in ('1', '2', 'X', '1X', 'X2', '12', 'Over 2.5', 'Under 2.5', 'BTTS Yes', 'BTTS No'):
            self.assertEqual(parse_tip(f'Tip: {value} Odds: 1.29'), value)
        for text in ('Tip: Overs', 'Tip: W', 'Odds: 1.29', 'Tip: 12x'):
            self.assertEqual(parse_tip(text), '')
    def test_suggests_only_score_separated_team_lines(self):
        self.assertEqual(parse_teams('Croatia 2-1 Czech Republic\nTip: 1'), ('Croatia','Czech Republic'))
        self.assertEqual(parse_teams('no match detected'), ('',''))
    def test_detects_repeated_headers(self):
        im=Image.new('RGB',(800,1280),'white');draw=ImageDraw.Draw(im)
        for y in (100, 278, 456, 634, 812, 990): draw.rectangle((30,y,770,y+32),fill='#e2e2e2')
        self.assertEqual(len(detect_cards(im)),6)
    def test_blank_image_no_cards(self):
        self.assertEqual(detect_cards(Image.new('RGB',(800,1280),'white')),[])
