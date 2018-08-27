"""Contains the KinAccount and AccountStatus classes."""

from functools import partial

from enum import Enum
from stellar_base.asset import Asset

from .blockchain.keypair import Keypair
from .blockchain.horizon import Horizon
from .blockchain.channel_manager import ChannelManager
from . import errors as KinErrors
from .config import MIN_ACCOUNT_BALANCE, SDK_USER_AGENT
from .blockchain.utils import is_valid_secret_key, is_valid_address


class KinAccount:
    """Account class to perform authenticated actions on the blockchain"""
    def __init__(self, seed, client, channels, channel_secret_keys, create_channels):
        # Set the internal sdk
        self._client = client

        # Verify seed
        if not is_valid_secret_key(seed):
            raise ValueError('invalid secret key: {}'.format(seed))

        # Set keypair
        self.keypair = Keypair(seed)
        # check that sdk wallet account exists and is activated
        if self._client.get_account_data(self.keypair.public_address) != AccountStatus.NOT_ACTIVATED:
            raise KinErrors.AccountNotActivatedError

        if channels is not None and channel_secret_keys is not None:
            raise ValueError("Account cannot be initialized with both 'channels'"
                             " and 'channel_secret_keys' parameters")

        if channel_secret_keys is not None:
            # Use given channels
            for channel_key in channel_secret_keys:
                # Verify channel seed
                if not is_valid_secret_key(channel_key):
                    raise ValueError('invalid channel key: {}'.format(channel_key))
                # Check that channel accounts exists (they do not have to be activated).
                channel_address = Keypair.address_from_seed(channel_key)
                if self._client.get_account_data(channel_address) != AccountStatus.NOT_CREATED:
                    raise KinErrors.AccountNotFoundError
            self.channel_secret_keys = channel_secret_keys

        elif channels is not None:
            # Generate the channels for the user
            self.channel_secret_keys = [Keypair.generate_hd_seed(seed, str(channel)) for channel in range(channels)]
        else:
            # Use the base account as the only channel
            self.channel_secret_keys = [seed]

        if create_channels:
            if channels is None:
                raise ValueError("create_channels can only be used with the channels parameter")

            # Create the channels using the base account
            if self.channel_secret_keys == [seed]:
                raise ValueError('There are no channels to create')
            base_account = KinAccount(seed,self._client, None, None, False)

            # Verify that there is enough XLM to create the channels
            # Balance should be at least (Number of channels + yourself) * (Minimum account balance + fees)
            if (len(self.channel_secret_keys) + 1) * (MIN_ACCOUNT_BALANCE + 0.00001) > \
                    base_account.get_balances()['XLM']:
                raise KinErrors.LowBalanceError('The base account does not have enough XLM to create the channels')

            # Create the channels, pass if the channel already exists
            for channel in self.channel_secret_keys:
                try:
                    # TODO: might want to make it a 1 multi operation tx
                    base_account.create_account(channel)
                except KinErrors.AccountExistsError:
                    pass

        # set connection pool size for channels + monitoring connection + extra
        pool_size = max(1, len(self.channel_secret_keys)) + 2

        # Set an horizon instance with the new pool_size
        self.horizon = Horizon(self._client.environment.horizon_uri,
                               pool_size=pool_size , user_agent=SDK_USER_AGENT)
        self.channel_manager = ChannelManager(seed, self.channel_secret_keys,
                                              self._client.environment.name, self.horizon)

    def get_public_address(self):
        """Return this KinAccount's public address"""
        return self.keypair.public_address

    def get_balances(self):
        """
        Get the KIN and XLM balance of this KinAccount
        :return: a dictionary containing the balances

        :raises: :class:`KinErrors.AccountNotFoundError`: if the account does not exist.
        """
        return self._client.get_account_balances(self.keypair.public_address)

    def get_data(self):
        """
        Gets this KinAccount's data

        :return: account data
        :rtype: :class:`kin.AccountData`

        :raises: :class:`KinErrors.AccountNotFoundError`: if the account does not exist.
        """
        return self._client.get_account_data(self.keypair.public_address)

    def create_account(self, address, starting_balance=MIN_ACCOUNT_BALANCE, memo_text=None):
        """Create an account identified by the provided address.

        :param str address: the address of the account to create.

        :param number starting_balance: (optional) the starting XLM balance of the account.
        If not provided, a default MIN_ACCOUNT_BALANCE will be used.

        # TODO: might want to limit this if we use tx_coloring
        :param str memo_text: (optional) a text to put into transaction memo, up to 28 chars.

        :return: the hash of the transaction
        :rtype: str

        :raises: ValueError: if the supplied address has a wrong format.
        :raises: :class:`KinErrors.AccountExistsError`: if the account already exists.
        """
        if not is_valid_address(address):
            raise ValueError('invalid address: {}'.format(address))

        try:
            reply = self.channel_manager.send_transaction(lambda builder:
                                                          partial(builder.append_create_account_op, address,
                                                                  starting_balance),
                                                          memo_text=memo_text)
            return reply['hash']
        except Exception as e:
            raise KinErrors.translate_error(e)

    def send_xlm(self, address, amount, memo_text=None):
        """Send XLM to the account identified by the provided address.

        :param str address: the account to send XLM to.

        :param number amount: the number of XLM to send.

        # TODO: might want to limit this if we do tx coloring
        :param str memo_text: (optional) a text to put into transaction memo.

        :return: the hash of the transaction
        :rtype: str

        :raises: ValueError: if the provided address has a wrong format.
        :raises: ValueError: if the amount is not positive.
        :raises: :class:`KinErrors.AccountNotFoundError`: if the account does not exist.
        :raises: :class:`KinErrors.LowBalanceError`: if there is not enough XLM to send and pay transaction fee.
        """
        return self._send_asset(Asset.native(), address, amount, memo_text)

    def send_kin(self, address, amount, memo_text=None):
        """Send KIN to the account identified by the provided address.

        :param str address: the account to send KIN to.

        :param number amount: the amount of KIN to send.

        # TODO: might want to limit this if we do tx coloring
        :param str memo_text: (optional) a text to put into transaction memo.

        :return: the hash of the transaction
        :rtype: str

        :raises: ValueError: if the provided address has a wrong format.
        :raises: ValueError: if the amount is not positive.
        :raises: :class:`KinErrors.AccountNotFoundError`: if the account does not exist.
        :raises: :class:`KinErrors.AccountNotActivatedError`: if the account is not activated.
        :raises: :class:`KinErrors.LowBalanceError`: if there is not enough KIN and XLM to send and pay transaction fee.
        """
        return self._send_asset(self._client.kin_asset, address, amount, memo_text)

    def monitor_kin_payments(self, callback_fn):
        """Monitor KIN payment transactions related to the this KinAccount.
        NOTE: the function starts a background thread.

        :param callback_fn: the function to call on each received payment as `callback_fn(address, tx_data)`.
        :type: callable[[str, :class:`kin.TransactionData`], None]

        :return: an event to stop the monitoring
        :rtype: threading.Event
        """
        return self._client.monitor_accounts_payments([self.keypair.public_address], callback_fn)

    # Internal methods

    def _send_asset(self, asset, address, amount, memo_text=None):
        """Send asset to the account identified by the provided address.

        :param str address: the account to send asset to.

        :param asset: asset to send
        :type: :class:`stellar_base.asset.Asset`

        :param number amount: the asset amount to send.

        :param str memo_text: (optional) a text to put into transaction memo.

        :return: the hash of the transaction
        :rtype: str

        :raises: ValueError: if the provided address has a wrong format.
        :raises: ValueError: if the amount is not positive.
        :raises: ValueError: if the amount is too precise
        :raises: :class:`kin.AccountNotFoundError`: if the account does not exist.
        :raises: :class:`kin.AccountNotActivatedError`: if the account is not activated for the asset.
        :raises: :class:`kin.LowBalanceError`: if there is not enough KIN and XLM to send and pay transaction fee.
        """

        if not is_valid_address(address):
            raise ValueError('invalid address: {}'.format(address))

        if amount <= 0:
            raise ValueError('amount must be positive')

        if amount * 1e7 % 1 != 0:
            raise ValueError('Number of digits after the decimal point in the amount exceeded the limit(7).')

        try:
            reply = self.channel_manager.send_transaction(lambda builder:
                                                          partial(builder.append_payment_op, address, amount,
                                                                  asset_type=asset.code, asset_issuer=asset.issuer),
                                                          memo_text=memo_text)
            return reply['hash']
        except Exception as e:
            raise KinErrors.translate_error(e)


class AccountStatus(Enum):
    # Account statuses enum
    NOT_CREATED = 1
    NOT_ACTIVATED = 2
    ACTIVATED = 3
