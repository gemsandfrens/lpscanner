import os
import json
import asyncio

from web3 import Web3
from web3.middleware import construct_sign_and_send_raw_middleware

from websockets.client import connect

from dotenv import load_dotenv

load_dotenv()


class ListingSniper:

    def __init__(self, trading_mode: bool = False, token: str = None):

        self.trading_mode = trading_mode
        self.token_to_snipe = token

        self.w3 = Web3(Web3.WebsocketProvider(os.environ.get("WSS_PROVIDER_URI")))
        self.account =self.w3.eth.account.from_key(os.environ.get("PRIVATE_KEY"))
        self.w3.middleware_onion.add(construct_sign_and_send_raw_middleware(self.account))

        with open("erc20_abi.json") as file:
            self.erc20_abi = json.load(file)

        with open("factory_abi.json") as file:
            self.factory_abi = json.load(file)

        with open("router_abi.json") as file:
            self.router_abi = json.load(file)

        # self.factory_contract = self.w3.eth.contract(
        #     address=os.environ.get("FACTORY_ADDRESS"),
        #     abi=self.factory_abi
        #     )

        self.router_contract = self.w3.eth.contract(
            address=os.environ.get("ROUTER_ADDRESS"),
            abi=self.router_abi
        )

    def handle_event(self, event: dict):
        '''
        processes incoming events emitted by the uniswap factory contract.
        '''
        
        topics = event["params"]["result"]["topics"] 

        # the first (formally 0-th) entry of the list of topics encodes the eventtype itself.
        token_0 = self.w3.to_checksum_address("0x" + topics[1][26:])
        token_1 = self.w3.to_checksum_address("0x" + topics[2][26:])

        token0_contract = self.w3.eth.contract(token_0, abi=self.erc20_abi)
        token0_symbol = token0_contract.functions.symbol().call()

        token1_contract = self.w3.eth.contract(token_1, abi=self.erc20_abi)
        token1_symbol = token1_contract.functions.symbol().call()

        print(f"pair created: ({token0_symbol}/{token1_symbol})")

        if self.trading_mode:

            if (token0_symbol == self.token_to_snipe) or token1_symbol == self.token_to_snipe:

                swap_tx = self.router_contract.functions.swapExactTokensForTokens(
                    amountIn=900,
                    amountOutMin=45,
                    path=[os.environ.get("USDC_CONTRACT_ADDRESS"), token_0],
                    to=os.environ.get("WALLET_ADDRESS"),
                )

                swap_tx.buildTransaction

        return

    async def run(self):

        async with connect(os.environ.get("WSS_PROVIDER_URI")) as socket:

            await socket.send(json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_subscribe",
                "params": [
                    "logs", 
                    {
                        "address": os.environ.get("FACTORY_ADDRESS"), 
                        "topics": [] # PairCreated is the only event.
                    }
                ]
            }))

            sub_res = await socket.recv()
            print(sub_res)

            while 1:
                try:
                    msg = await asyncio.wait_for(socket.recv(), timeout=15)
                    event = json.loads(msg)
                    self.handle_event(event)
                except:
                    pass

if __name__ == "__main__":
    sniper = ListingSniper()
    asyncio.run(sniper.run())
