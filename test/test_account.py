import pytest
from kin import KinErrors
from kin.config import MEMO_TEMPLATE, ANON_APP_ID
from time import sleep

SDK_PUBLIC = 'GAIDUTTQ5UIZDW7VZ2S3ZAFLY6LCRT5ZVHF5X3HDJVDQ4OJWYGJVJDZB'
SDK_SEED = 'SBKI7MEF62NHHH3AOXBHII46K2FD3LVH63FYHUDLTBUYT3II6RAFLZ7B'


def test_create_basic(test_client, test_account):
    with pytest.raises(KinErrors.StellarSecretInvalidError):
        account = test_client.kin_account('bad format')

    account = test_client.kin_account(SDK_SEED)
    assert account
    assert account.keypair.secret_seed == SDK_SEED
    assert account.keypair.public_address == SDK_PUBLIC
    assert account._client is test_client
    assert account.channel_manager


def test_get_address(test_client, test_account):
    assert test_account.get_public_address() == SDK_PUBLIC


@pytest.mark.asyncio
async def test_create_account(setup, test_client, test_account):
    with pytest.raises(KinErrors.AccountExistsError):
        await test_account.create_account(setup.issuer_address, 0, fee=100)

    await test_account.create_account('GDN7KB72OO7G6VBD3CXNRFXVELLW6F36PS42N7ASZHODV7Q5GYPETQ74', 0, fee=100)
    assert await test_client.does_account_exists('GDN7KB72OO7G6VBD3CXNRFXVELLW6F36PS42N7ASZHODV7Q5GYPETQ74')


@pytest.mark.asyncio
async def test_send_kin(test_client, test_account):
    recipient = 'GBZWWLRJRWL4DLYOJMCHXJUOJJY5NLNJHQDRQHVQH43KFCPC3LEOWPYM'
    await test_client.friendbot(recipient)

    await test_account.send_kin(recipient, 10, fee=100)
    balance = await test_client.get_account_balance(recipient)
    with pytest.raises(KinErrors.NotValidParamError):
        await test_account.send_kin(recipient, 1.1234567898765, fee=100)
    assert balance == 10


def test_build_create_account(test_account):
    recipient = 'GBZWWLRJRWL4DLYOJMCHXJUOJJY5NLNJHQDRQHVQH43KFCPC3LEOWPYM'
    with pytest.raises(KinErrors.StellarAddressInvalidError):
        test_account.build_create_account('bad address', 0, fee=100)
    with pytest.raises(KinErrors.NotValidParamError):
        test_account.build_create_account(recipient, 0, memo_text='a' * 50, fee=100)
    with pytest.raises(ValueError):
        test_account.build_create_account(recipient, -1, fee=100)

    builder = test_account.build_create_account(recipient, starting_balance=10, fee=100)

    assert builder


def test_build_send_kin(test_account):
    recipient = 'GBZWWLRJRWL4DLYOJMCHXJUOJJY5NLNJHQDRQHVQH43KFCPC3LEOWPYM'
    with pytest.raises(KinErrors.StellarAddressInvalidError):
        test_account.build_send_kin('bad address', 0, fee=100)
    with pytest.raises(KinErrors.NotValidParamError):
        test_account.build_send_kin(recipient, 10, memo_text='a' * 50, fee=100)
    with pytest.raises(ValueError):
        test_account.build_send_kin(recipient, -50, fee=100)

    builder = test_account.build_send_kin(recipient, 10, fee=100)

    assert builder


@pytest.mark.asyncio
async def test_auto_top_up(test_client, test_account):
    channel = 'SBYU2EBGTTGIFR4O4K4SQXTD4ISMVX4R5TX2TTB4SWVIA5WVRS2MHN4K'
    public = 'GBKZAXTDJRYBK347KDTOFWEBDR7OW3U67XV2BOF2NLBNEGRQ2WN6HFK6'
    await test_account.create_account(public, 0, fee=100)

    account = test_client.kin_account(test_account.keypair.secret_seed, channel_secret_keys=[channel])
    await account.send_kin(public, 10, fee=100)

    channel_balance = await test_client.get_account_balance(public)
    # channel should have ran out of funds, so the base account should have topped it up
    assert channel_balance > 0


@pytest.mark.asyncio
async def test_memo(test_client, test_account):
    recipient1 = 'GCT3YLKNVEILHUOZYK3QPOVZWWVLF5AE5D24Y6I4VH7WGZYBFU2HSXYX'
    recipient2 = 'GDR375ZLWHZUFH2SWXFEH7WVPK5G3EQBLXPZKYEFJ5EAW4WE4WIQ5BP3'

    tx1 = await test_account.create_account(recipient1, 0, memo_text='Hello', fee=100)
    account2 = test_client.kin_account(test_account.keypair.secret_seed, app_id='test')
    tx2 = await account2.create_account(recipient2, 0, memo_text='Hello', fee=100)
    sleep(5)

    tx1_data = await test_client.get_transaction_data(tx1)
    tx2_data = await test_client.get_transaction_data(tx2)

    assert tx1_data.memo == MEMO_TEMPLATE.format(ANON_APP_ID) + 'Hello'
    assert tx2_data.memo == MEMO_TEMPLATE.format('test') + 'Hello'

    with pytest.raises(KinErrors.NotValidParamError):
        await account2.create_account(recipient2, 0, memo_text='a'*25, fee=100)


def test_get_transaction_builder(test_account):
    builder = test_account.get_transaction_builder(fee=100)
    assert builder
    assert builder.address == test_account.get_public_address()
    assert builder.fee == 100
    assert builder.horizon is test_account._client.horizon
    assert builder.network_name == test_account._client.environment.name


def test_whitelist_transaction(test_account):
    b64_tx = 'AAAAAMEn3A7DfkYAE259RhMg6JoCLdnK1i47kf3GT4UE0G36AAAAAQAAAMEAAAADAAAAAAAAAAEAAAAHMS1hbm9uLQAAAAABAAAAAAAAAAAAAAAAjEk8J7p+a70GMVmlyXKkfbYKr1zBrmE9Zds3LRCkENwAAAAAAAGGoAAAAAAAAAABBNBt+gAAAEDd/M9PA0Iw9I/DUs0ElPV9FFP/ih5zNYJFKrbecXUaBfbRzjIvdg7BFRycVaJrBkhxy0cYWypPQge+Mku/fXoM'
    net_id = 'Integration Test Network ; zulucrypto'
    whitelisted_tx = test_account.whitelist_transaction({'envelop':b64_tx, 'network_id': net_id})

    assert whitelisted_tx == 'AAAAAMEn3A7DfkYAE259RhMg6JoCLdnK1i47kf3GT4UE0G36AAAAAQAAAMEAAAADAAAAAAAAAAEAAAAHMS1hbm9uLQAAAAABAAAAAAAAAAAAAAAAjEk8J7p+a70GMVmlyXKkfbYKr1zBrmE9Zds3LRCkENwAAAAAAAGGoAAAAAAAAAACBNBt+gAAAEDd/M9PA0Iw9I/DUs0ElPV9FFP/ih5zNYJFKrbecXUaBfbRzjIvdg7BFRycVaJrBkhxy0cYWypPQge+Mku/fXoMNsGTVAAAAEDFTrPyqr0ultlwbyceYOc61w381t17UiKgtZrXgdySduKfBxifWDm8R8moOBSfY5pZi3Gfp+vAG7wS9YkU4zcF'
