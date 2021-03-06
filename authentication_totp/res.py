# This file is part of the authentication_totp Tryton module.
# Please see the COPYRIGHT and README.rst files at the top level of this
# package for full copyright notices, license terms and support information.
from binascii import Error as BinAsciiError
from io import BytesIO
from math import ceil
from passlib.exc import TokenError, UsedTokenError
from passlib.totp import TOTP
try:
    from qrcode import QRCode
    from qrcode.image.pil import PilImage
except ImportError:
    QRCode = None

from trytond.config import config
from trytond.i18n import gettext
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval

from .exception import (
    TOTPAccessCodeReuseError, TOTPInvalidSecretError, TOTPKeyTooShortError,
    TOTPKeyTooShortWarning, TOTPLoginException)
from .model import UserPreferencesButton

_totp_issuer = config.get(
    'authentication_totp', 'issuer', default='{company} Tryton')
_totp_key_length = config.get(
    'authentication_totp', 'key_length', default=160)

_TOTPFactory = TOTP.using(secrets_path=config.get(
    'authentication_totp', 'application_secrets_file', default=None))


class User(metaclass=PoolMeta):
    __name__ = 'res.user'

    totp_key = fields.Char("TOTP Key")
    totp_secret = fields.Function(fields.Char(
            "TOTP Secret",
            help="Secret key used for time-based one-time password (TOTP) "
            "user authentication."),
        'on_change_with_totp_secret', setter='set_totp_secret')
    totp_qrcode = fields.Function(fields.Binary(
            "TOTP QR Code",
            states={
                'invisible': ~Eval('totp_secret', '') or (not QRCode),
                },
            depends=['totp_secret'],
            help="The QR code for the secret key. Used with authenticator "
            "apps."),
        'on_change_with_totp_qrcode')
    totp_url = fields.Function(fields.Char(
            "TOTP URL",
            states={
                'invisible': ~Eval('totp_secret', ''),
                },
            depends=['totp_secret'],
            help="The URL that contains the secret key and which gets encoded "
            "into a QR Code."),
        'on_change_with_totp_url')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._preferences_fields.extend([
            'totp_secret',
            ])
        cls._buttons.update({
            'update_totp_secret': UserPreferencesButton(),
            })

    @fields.depends('totp_key')
    def on_change_with_totp_secret(self, name=None):
        if self.totp_key:
            totp = _TOTPFactory.from_json(self.totp_key)
            return totp.pretty_key()

    def _get_totp_issuer_fields(self):
        return {
            'company': "",
            }

    @fields.depends(
        'login', 'totp_secret', methods=['_get_totp_issuer_fields'])
    def on_change_with_totp_url(self, name=None):
        if not self.totp_secret:
            return
        issuer = _totp_issuer.format(**self._get_totp_issuer_fields())
        issuer = issuer.strip()
        totp = _TOTPFactory(key=self.totp_secret)
        return totp.to_uri(label=self.login, issuer=issuer)

    @fields.depends('totp_secret', 'totp_url')
    def on_change_with_totp_qrcode(self, name=None):
        url = self.on_change_with_totp_url()
        if not url or not QRCode:
            return

        data = BytesIO()
        qr = QRCode(image_factory=PilImage)
        qr.add_data(url)
        image = qr.make_image()
        image.save(data)
        return data.getvalue()

    @classmethod
    def _totp_admin(cls):
        ModelAccess = Pool().get('ir.model.access')
        return ModelAccess.check(
            'res.user', mode='write', raise_exception=False)

    @classmethod
    def _totp_key_length_too_short(cls, key):
        if key:
            totp = _TOTPFactory.from_json(key)
            key_length = len(totp.key) * 8
            return key_length < _totp_key_length

    @classmethod
    def set_totp_secret(cls, users, name, value):
        Warning = Pool().get('res.user.warning')

        if value:
            try:
                key = _TOTPFactory(key=value).to_json()
            except BinAsciiError:
                raise TOTPInvalidSecretError(gettext(
                    'authentication_totp.msg_user_invalid_totp_secret',
                    login=users[0].login))
        else:
            key = None

        if cls._totp_admin() and cls._totp_key_length_too_short(key):
            warning_name = 'authentication_totp.key_too_short'
            if Warning.check(warning_name):
                raise TOTPKeyTooShortWarning(warning_name, gettext(
                    'authentication_totp.msg_user_totp_too_short',
                    login=users[0].login))

        cls.write(list(users), {
            'totp_key': key,
            })

    @classmethod
    def generate_totp_secret(cls):
        size = ceil(_totp_key_length / 8)
        return _TOTPFactory.new(size=size).pretty_key()

    @ModelView.button_change('totp_secret')
    def update_totp_secret(self):
        self.totp_secret = self.generate_totp_secret()

    @classmethod
    def validate(cls, users):
        admin = cls._totp_admin()
        for user in users:
            if not admin and cls._totp_key_length_too_short(user.totp_key):
                raise TOTPKeyTooShortError(gettext(
                    'authentication_totp.msg_user_totp_too_short',
                    login=user.login))

    @classmethod
    def _login_totp(cls, login, parameters):
        TOTPLogin = Pool().get('res.user.login.totp')

        user_id = cls._get_login(login)[0]
        if not user_id:
            return

        if TOTPLogin.parameter not in parameters:
            raise TOTPLoginException(TOTPLogin.parameter, login)

        access_code = parameters[TOTPLogin.parameter]
        totp_login = TOTPLogin.get(user_id)
        if totp_login.check(access_code):
            return user_id


class UserCompany(metaclass=PoolMeta):
    __name__ = 'res.user'

    @fields.depends('main_company')
    def _get_totp_issuer_fields(self):
        company = self.main_company.rec_name if self.main_company else ""
        return {
            'company': company,
            }


class UserLoginTOTP(ModelSQL):
    "User Login TOTP"
    __name__ = 'res.user.login.totp'

    user_id = fields.Integer("User ID")
    user = fields.Function(fields.Many2One('res.user', "User"), 'get_user')
    last_counter = fields.Integer("Last Counter")

    parameter = 'totp_code'

    def get_user(self, name):
        return self.user_id

    @classmethod
    def get(cls, user_id):
        records = cls.search([
            ('user_id', '=', user_id),
            ])
        if records:
            record = records.pop()
            if records:
                cls.delete(records)
            return record
        else:
            record = cls(user_id=user_id)
            record.save()
            return record

    def check(self, code, _time=None):
        if not self.user.totp_key:
            return

        try:
            counter, _ = _TOTPFactory.verify(
                code, self.user.totp_key, time=_time,
                last_counter=self.last_counter)
        except UsedTokenError:
            # Warn the user the token has already been used
            raise TOTPAccessCodeReuseError(self.parameter, self.user.login)
        except TokenError:
            return

        self.last_counter = counter
        self.save()

        return True
