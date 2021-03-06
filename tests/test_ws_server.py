import unittest
import json
import uuid

from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from noughts_and_crosses.game import (
    Game, BoxType, Player, GameStatus
)
from noughts_and_crosses.app import get_application


class WebsocketServerTestCase(AioHTTPTestCase):

    async def get_application(self, loop):
        return get_application(loop)

    async def connect_player(self):
        player_id = str(uuid.uuid4())
        ws = await self.client.ws_connect(
            '/ws',
            headers={
                'Cookie': 'player_id={player_id}'.format(
                    player_id=player_id
                )
            }
        )
        return Player(id=player_id, ws=ws)

    async def connect_players(self):
        self.players = [
            await self.connect_player(),
            await self.connect_player()
        ]
        self.assertDictEqual(
            json.loads((await self.players[0].ws.receive()).data),
            {
                'payload': {
                    'whose_turn': None,
                    'grid': [BoxType.empty] * Game.grid_size * Game.grid_size,
                    'winner': None,
                    'status': GameStatus.awaiting
                },
                'event': 'game_state'
            }
        )

        response = json.loads((await self.players[0].ws.receive()).data)
        self.assertDictEqual(
            response,
            json.loads((await self.players[1].ws.receive()).data)
        )

        whose_turn = response['payload']['whose_turn']
        if self.players[0].id == whose_turn:
            self.acting, self.awaiting = self.players
        else:
            self.acting, self.awaiting = self.players[::-1]

    async def turn(self, box_num, expected_game_status, expected_winner=None):
        await self.acting.ws.send_json(
            {'operation': 'turn', 'payload': {'turn': box_num}}
        )

        response_1 = json.loads((await self.acting.ws.receive()).data)
        response_2 = json.loads((await self.awaiting.ws.receive()).data)
        self.assertDictEqual(response_1, response_2)

        self.assertTrue(response_1['payload']['grid'][box_num] != BoxType.empty)
        self.assertTrue(response_1['payload']['winner'] == expected_winner)
        self.assertTrue(response_1['payload']['status'] == expected_game_status)

        whose_turn = response_1['payload']['whose_turn']
        if self.players[0].id == whose_turn:
            self.acting, self.awaiting = self.players
        else:
            self.acting, self.awaiting = self.players[::-1]

    @unittest_run_loop
    async def test_winning_the_game(self):
        await self.connect_players()

        await self.turn(box_num=0, expected_game_status=GameStatus.in_progress)
        await self.turn(box_num=1, expected_game_status=GameStatus.in_progress)
        await self.turn(box_num=3, expected_game_status=GameStatus.in_progress)
        await self.turn(box_num=4, expected_game_status=GameStatus.in_progress)
        await self.turn(
            box_num=6,
            expected_game_status=GameStatus.finished,
            expected_winner=self.acting.id
        )

    @unittest_run_loop
    async def test_drawn_game(self):
        await self.connect_players()

        await self.turn(box_num=0, expected_game_status=GameStatus.in_progress)
        await self.turn(box_num=1, expected_game_status=GameStatus.in_progress)
        await self.turn(box_num=2, expected_game_status=GameStatus.in_progress)
        await self.turn(box_num=4, expected_game_status=GameStatus.in_progress)
        await self.turn(box_num=7, expected_game_status=GameStatus.in_progress)
        await self.turn(box_num=6, expected_game_status=GameStatus.in_progress)
        await self.turn(box_num=8, expected_game_status=GameStatus.in_progress)
        await self.turn(box_num=5, expected_game_status=GameStatus.in_progress)
        await self.turn(box_num=3, expected_game_status=GameStatus.finished)

    @unittest_run_loop
    async def test_unfinished_game(self):
        await self.connect_players()

        await self.acting.ws.close()
        response = json.loads((await self.awaiting.ws.receive()).data)
        self.assertEqual(response['payload']['status'], GameStatus.unfinished)

    @unittest_run_loop
    async def test_server_errors(self):
        ws = await self.client.ws_connect('/ws')
        response_1 = json.loads((await ws.receive()).data)
        self.assertDictEqual(
            response_1,
            {
                'event': 'error',
                'payload': {'message': 'player_id cookie required'}
            }
        )

        await self.connect_players()
        await self.awaiting.ws.send_json(
            {'operation': 'turn', 'payload': {'turn': 0}}
        )
        response = json.loads((await self.awaiting.ws.receive()).data)
        self.assertDictEqual(
            response,
            {'event': 'error', 'payload': {'message': 'Not your turn'}}
        )

        await self.turn(box_num=0, expected_game_status=GameStatus.in_progress)
        await self.acting.ws.send_json(
            {'operation': 'turn', 'payload': {'turn': 0}}
        )
        response = json.loads((await self.acting.ws.receive()).data)
        self.assertDictEqual(
            response,
            {
                'event': 'error',
                'payload': {'message': 'Box is not empty. Try again.'}
            }
        )

if __name__ == '__main__':
    unittest.main()
