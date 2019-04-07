import pytest

import asyncio
from kin import Environment, KinClient

import logging

logging.basicConfig()


@pytest.fixture(scope='session')
def setup():
    # Set setup values
    class Struct:
        """Handy variable holder"""

        def __init__(self, **entries): self.__dict__.update(entries)

    # Using a local blockchain, this is the root account
    issuer_seed = 'SDPTXNTPCU6DXIY2YOAQYFRQZEKHC5FJEWJUF2HQ24DUFLSHOVTCS6B2'
    issuer_address = 'GA3FLH3EVYHZUHTPQZU63JPX7ECJQL2XZFCMALPCLFYMSYC4JKVLAJWM'
    docker_environment = Environment('DOCKER', 'http://localhost:8008',
                                     'Integration Test Network ; zulucrypto', 'http://localhost:8001')

    print('Testing with environment:', docker_environment)
    return Struct(issuer_address=issuer_address,
                  issuer_seed=issuer_seed,
                  environment=docker_environment)


@pytest.yield_fixture(scope='session')
async def test_client(setup):
    # Create a base KinClient
    print('Created a base KinClient')
    client = KinClient(setup.environment)
    yield client
    await client.__aexit__(None, None, None)


@pytest.fixture(scope='session')
async def test_account(setup, test_client):
    # Create and fund the sdk account from the root account

    sdk_address = 'GAIDUTTQ5UIZDW7VZ2S3ZAFLY6LCRT5ZVHF5X3HDJVDQ4OJWYGJVJDZB'
    sdk_seed = 'SBKI7MEF62NHHH3AOXBHII46K2FD3LVH63FYHUDLTBUYT3II6RAFLZ7B'

    root_account = test_client.kin_account(setup.issuer_seed)
    await root_account.create_account(sdk_address, 10000 + 1000000, fee=100)
    print('Created the base kin account')
    return test_client.kin_account(sdk_seed)


@pytest.yield_fixture(scope='session')
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
