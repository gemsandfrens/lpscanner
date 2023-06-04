import os
import json
import asyncio
import requests

from typing import List 

from web3 import Web3
from web3.middleware import construct_sign_and_send_raw_middleware

from Crypto.Hash import keccak

from websockets.client import connect

from dotenv import load_dotenv


load_dotenv()


class ListingSniper:

    def __init__(self, token: str = None):

        self.token_to_snipe = token

        self.w3 = Web3(Web3.WebsocketProvider(os.environ.get("WSS_PROVIDER_URI")))
        self.account = self.w3.eth.account.from_key(os.environ.get("PRIVATE_KEY"))
        self.w3.middleware_onion.add(construct_sign_and_send_raw_middleware(self.account))

        self.universal_router_contract = self.w3.eth.contract(
            address=os.environ.get("UNIVERSAL_ROUTER_ADDRESS")
            )
        
        bot_token = os.environ.get("TG_BOT_TOKEN")
        chat_id = os.environ.get("BANTER_ID")
        self.tg_bot_url = f"https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={chat_id}&text="

        with open("erc20_abi.json") as file:
            self.erc20_abi = json.load(file)

    async def handle_event(self, event: dict):
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
        
        sub_hash = event["params"]["subscription"]

        url = self.tg_bot_url + f"{token0_symbol} / {token1_symbol}\n{token0_contract}\n{token1_contract}"
        requests.get(url)    

        if token0_symbol == self.token_to_snipe or token1_symbol == self.token_to_snipe:
            
            if sub_hash == self.v3_sub_hash:
                # do v3 shit
                pass
            elif sub_hash == self.v2_sub_hash:
                pass # do v2 shit

        return
    
    @staticmethod
    async def subscribe(socket, address: str, topics: List[str] = []):
        data = dict(
            jsonrpc="2.0", 
            id=1, 
            method="eth_subscribe", 
            params=["logs", dict(address=address, topics=topics)]
            )
        await socket.send(json.dumps(data))

    @staticmethod
    def encode_event_sig(sig: str):
        k = keccak.new(digest_bits=256)
        k.update(sig.encode())
        return "0x" + str(k.hexdigest())
    
    async def run(self):

        v3 = os.environ.get("V3_FACTORY_ADDRESS")
        v2 = os.environ.get("V2_FACTORY_ADDRESS")

        async with connect(os.environ.get("ARBITRUM_WSS_URI")) as socket:
            pool_created_topic = self.encode_event_sig(
                "PoolCreated(address,address,uint24,int24,address)"
                )

            # subscribing to the v3 first ...
            await self.subscribe(socket, v3, [pool_created_topic])
            v3_sub_res = await socket.recv()
            self.v3_sub_hash = json.loads(v3_sub_res)["result"]
            print("subscribed to v3 events:", self.v3_sub_hash)

            # now the v2 event
            await self.subscribe(socket, v2, [])
            v2_sub_res = await socket.recv()
            self.v2_sub_hash = json.loads(v2_sub_res)["result"]

            print("subscribed to v2 events:", self.v2_sub_hash)

            while 1:

                try:
                    msg = await asyncio.wait_for(socket.recv(), timeout=15)
                    event = json.loads(msg)
                    await self.handle_event(event)
                    
                except:
                    pass

if __name__ == "__main__":
    sniper = ListingSniper()
    asyncio.run(sniper.run())
