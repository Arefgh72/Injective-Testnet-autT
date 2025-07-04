# scripts/run_transactions.py

import os
import json
import time
from datetime import datetime, timedelta
import pytz # برای مدیریت دقیق زمان‌های UTC
from web3 import Web3, HTTPProvider
from eth_account import Account
from eth_utils import to_checksum_address, decode_hex, encode_hex

# --- 1. تنظیمات (Configuration) ---

# کلید خصوصی از متغیرهای محیطی GitHub Secret خوانده می‌شود
PRIVATE_KEY = os.environ.get('INJECTIVE_PRIVATE_KEY')
if not PRIVATE_KEY:
    print('❌ خطا: متغیر محیطی INJECTIVE_PRIVATE_KEY تنظیم نشده است.')
    exit(1)

# بررسی حالت تست (TEST_MODE)
IS_TEST_MODE = os.environ.get('TEST_MODE') == 'true'
if IS_TEST_MODE:
    print('🧪 حالت تست فعال است. تمام تراکنش‌ها بدون بررسی زمان‌بندی اجرا خواهند شد.')

# اطلاعات شبکه Injective Testnet
# RPC_URL اصلی و صحیح شما
RPC_URL = 'https://k8s.testnet.json-rpc.injective.network/'
CHAIN_ID = 1439  # Chain ID تست‌نت Injective

# تنظیمات Web3
# استفاده از HTTPProvider با تنظیمات سفارشی برای سازگاری بیشتر
w3 = Web3(HTTPProvider(
    RPC_URL,
    request_kwargs={
        'timeout': 60,  # افزایش زمان timeout به 60 ثانیه
        'verify': True, # بررسی گواهینامه‌های SSL
        'proxies': None # اطمینان از عدم استفاده از پراکسی
    }
))
# برای غیرفعال کردن keepAlive و disableBatch، اینها تنظیمات داخلی Web3.py نیستند
# اما HttpProvider به صورت پیش‌فرض اتصالات رو به درستی مدیریت می‌کنه

# اطمینان از اتصال به شبکه
if not w3.is_connected():
    print(f'❌ خطا: اتصال به RPC Endpoint {RPC_URL} برقرار نشد.')
    exit(1)
print(f'✅ اتصال به شبکه {RPC_URL} برقرار شد.')

# آدرس فرستنده (کیف پول شما) که از کلید خصوصی مشتق می‌شود
account = Account.from_key(PRIVATE_KEY)
SENDER_ADDRESS = to_checksum_address(account.address)
print(f'✅ آدرس کیف پول فرستنده: {SENDER_ADDRESS}')

# آدرس قراردادها و توکن‌ها (به‌روزرسانی شده با آدرس‌های رسمی شما)
CONTRACT_ADDRESSES = {
    'STAKING': to_checksum_address('0x494401396FD1cf51cDD13e29eCFA769F49e1F5D3'),
    'WARP_UNWARP_WINJ': to_checksum_address('0x0000000088827d2d103ee2d9A6b781773AE03FfB'), # wINJ رسمی برای Warp/Unwarp
    'DEX_BSWAP': to_checksum_address('0x822f872763B7Be16c9b9687D8b9D73f1b5017Df0'),
    'USDT_TOKEN': to_checksum_address('0xaDC7bcB5d8fe053Ef19b4E0C861c262Af6e0db60'), # USDT رسمی
    'SWAP_WINJ_TOKEN': to_checksum_address('0x0000000088827d2d103ee2d9A6b781773AE03FfB'), # wINJ رسمی برای Swap (همان wINJ Warp/Unwrap)
}

# تعداد ارقام اعشار برای هر توکن
TOKEN_DECIMALS = {
    'INJ': 18,
    'USDT': 6,
    'SWAP_WINJ': 18,
}

# قیمت و گس لیمیت ثابت (بر اساس نمونه‌های ارسالی شما)
FIXED_GAS_PRICE_WEI = w3.to_wei('0.192', 'gwei') # تبدیل 0xb71b000 به گوی، یا مستقیم 0x به دسیمال
# از 0xb71b000 به دسیمال 19200000000 میرسه که 19.2 گوی میشه. در نمونه شما 0.192 گوی بود.
# با توجه به اینکه شما 0.3 گوی هم گفتید، فرض بر اینه که 0.192 گوی مورد نظره.
# اگه 0xb71b000 دقیقاً باید باشه، باید بنویسیم w3.to_int(hexstr='0xb71b000')

GAS_LIMITS = {
    'STAKE': 5297304,
    'WARP': 52619,
    'UNSTAKE': 6623965,
    'SWAP': 657795,
}

# مسیر فایل برای ذخیره خروجی سواپ‌های دینامیک
SWAP_OUTPUTS_FILE = 'data/swap_outputs.json'

# پیکربندی تمام تراکنش‌ها با زمان‌بندی و جزئیات
ALL_TRANSACTIONS = [
    {
        'name': 'استیک (Stake)',
        'type': 'STAKE',
        'contract': CONTRACT_ADDRESSES['STAKING'],
        'method_id': '0x8aa2799c',
        'value': '0.1',  # 0.1 INJ
        'repeats': 1,
        'gas_limit': GAS_LIMITS['STAKE'],
        'schedule': {'hour': 5, 'minute': 30},  # 05:30 UTC
    },
    {
        'name': 'وارپ (Warp)',
        'type': 'WARP',
        'contract': CONTRACT_ADDRESSES['WARP_UNWARP_WINJ'],
        'method_id': '0xd0e30db0',  # deposit()
        'value': '0.001',  # 0.001 INJ
        'repeats': 50,
        'gas_limit': GAS_LIMITS['WARP'],
        'schedule': [
            {'hour': 6, 'minute': 0},
            {'hour': 9, 'minute': 0},
            {'hour': 14, 'minute': 0},
            {'hour': 18, 'minute': 0},
            {'hour': 23, 'minute': 0},
        ],
    },
    {
        'name': 'آن‌استیک (Unstake)',
        'type': 'UNSTAKE',
        'contract': CONTRACT_ADDRESSES['STAKING'],
        'method_id': '0xc9107def',
        'amount': '0.09',  # 0.09 INJ (as parameter in data)
        'repeats': 1,
        'gas_limit': GAS_LIMITS['UNSTAKE'],
        'schedule': {'hour': 14, 'minute': 10},  # 14:10 UTC
    },
    {
        'name': 'سواپ USDT به wINJ',
        'type': 'SWAP_USDT_TO_WINJ',
        'contract': CONTRACT_ADDRESSES['DEX_BSWAP'],
        'method_id': '0x414bf389',
        'input_amount': '0.01',  # 0.01 USDT
        'input_token_address': CONTRACT_ADDRESSES['USDT_TOKEN'],
        'output_token_address': CONTRACT_ADDRESSES['SWAP_WINJ_TOKEN'],
        'min_amount_out': '1',  # 1 wei of wINJ (خیلی کوچک برای تست‌نت)
        'recipient': SENDER_ADDRESS,
        'repeats': 1,
        'gas_limit': GAS_LIMITS['SWAP'],
        'schedule': [
            {'hour': 12, 'minute': 0},
            {'hour': 19, 'minute': 0},
        ],
    },
    {
        'name': 'سواپ wINJ به USDT',
        'type': 'SWAP_WINJ_TO_USDT',
        'contract': CONTRACT_ADDRESSES['DEX_BSWAP'],
        'method_id': '0x414bf389',
        'input_token_address': CONTRACT_ADDRESSES['SWAP_WINJ_TOKEN'],
        'output_token_address': CONTRACT_ADDRESSES['USDT_TOKEN'],
        'min_amount_out': '1',  # 1 wei of USDT (خیلی کوچک برای تست‌نت)
        'recipient': SENDER_ADDRESS,
        'repeats': 1,
        'gas_limit': GAS_LIMITS['SWAP'],
        'schedule': [
            {'hour': 20, 'minute': 0},
            {'hour': 0, 'minute': 0},  # 24:00 UTC
        ],
    },
]

# --- 2. توابع کمکی (Helper Functions) ---

def to_smallest_unit(amount: str, decimals: int) -> int:
    """تبدیل مقدار توکن خوانا به کوچکترین واحد بر اساس اعشار."""
    try:
        # استفاده از دسیمال برای توکن‌ها
        amount_float = float(amount)
        return int(amount_float * (10 ** decimals))
    except ValueError:
        print(f"❌ خطا: مقدار نامعتبر '{amount}' برای تبدیل به کوچکترین واحد.")
        exit(1)

def from_smallest_unit(amount_in_smallest_unit: int, decimals: int) -> str:
    """تبدیل مقدار از کوچکترین واحد به فرمت خوانا."""
    try:
        # استفاده از دسیمال برای توکن‌ها
        return str(amount_in_smallest_unit / (10 ** decimals))
    except ValueError:
        print(f"❌ خطا: مقدار نامعتبر '{amount_in_smallest_unit}' برای تبدیل از کوچکترین واحد.")
        return "0"

def read_swap_outputs():
    """خواندن خروجی‌های سواپ از فایل JSON."""
    try:
        if not os.path.exists(SWAP_OUTPUTS_FILE):
            print(f'ℹ️ فایل {SWAP_OUTPUTS_FILE} وجود ندارد، در حال ایجاد فایل جدید...')
            initial_data = {"12:00": "0", "19:00": "0"}
            os.makedirs(os.path.dirname(SWAP_OUTPUTS_FILE), exist_ok=True)
            with open(SWAP_OUTPUTS_FILE, 'w') as f:
                json.dump(initial_data, f, indent=2)
            return initial_data
        with open(SWAP_OUTPUTS_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f'❌ خطا در خواندن فایل {SWAP_OUTPUTS_FILE} (JSON نامعتبر): {e}')
        return {"12:00": "0", "19:00": "0"}
    except Exception as e:
        print(f'❌ خطا در خواندن فایل {SWAP_OUTPUTS_FILE}: {e}')
        return {"12:00": "0", "19:00": "0"}

def write_swap_outputs(data):
    """نوشتن خروجی‌های سواپ در فایل JSON."""
    try:
        os.makedirs(os.path.dirname(SWAP_OUTPUTS_FILE), exist_ok=True)
        with open(SWAP_OUTPUTS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f'✅ فایل {SWAP_OUTPUTS_FILE} به‌روزرسانی شد.')
    except Exception as e:
        print(f'❌ خطا در نوشتن در فایل {SWAP_OUTPUTS_FILE}: {e}')

def send_transaction(to_address, value, gas_limit, data, nonce):
    """ارسال یک تراکنش امضا شده."""
    try:
        transaction = {
            'from': SENDER_ADDRESS,
            'to': to_checksum_address(to_address),
            'value': value, # مقدار باید به wei باشد
            'gas': gas_limit,
            'gasPrice': FIXED_GAS_PRICE_WEI,
            'nonce': nonce,
            'chainId': CHAIN_ID,
            'data': data
        }
        
        # امضای تراکنش
        signed_transaction = w3.eth.account.sign_transaction(transaction, private_key=PRIVATE_KEY)
        
        print(f'🚀 در حال ارسال تراکنش به: {to_checksum_address(to_address)}، Nonce: {nonce}، Value: {w3.from_wei(value, "ether") if value > 0 else 0} INJ')
        
        # ارسال تراکنش
        tx_hash = w3.eth.send_raw_transaction(signed_transaction.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        print(f'✅ تراکنش موفق! هش: {encode_hex(receipt.transactionHash)}')
        return receipt
    except Exception as e:
        print(f'❌ خطا در ارسال تراکنش به {to_address} (Nonce: {nonce}): {e}')
        raise # خطا را به تابع فراخواننده برمی‌گردانیم

# --- 3. توابع اجرای تراکنش‌های خاص ---

def execute_stake(nonce):
    """اجرای تراکنش استیک."""
    print('\n--- 🥩 در حال اجرای تراکنش استیک ---')
    config = next((t for t in ALL_TRANSACTIONS if t['type'] == 'STAKE'), None)
    if not config: return nonce

    value_in_wei = w3.to_wei(config['value'], 'ether') # INJ دارای 18 رقم اعشار

    try:
        receipt = send_transaction(
            to_address=config['contract'],
            value=value_in_wei,
            gas_limit=config['gas_limit'],
            data=config['method_id'],
            nonce=nonce
        )
        return nonce + 1
    except Exception:
        print('❌ تراکنش استیک شکست خورد.')
        return nonce

def execute_warp(nonce, repeats):
    """اجرای تراکنش وارپ."""
    print(f'\n--- 🔄 در حال اجرای تراکنش وارپ ({repeats} بار) ---')
    config = next((t for t in ALL_TRANSACTIONS if t['type'] == 'WARP'), None)
    if not config: return nonce

    value_in_wei = w3.to_wei(config['value'], 'ether') # INJ دارای 18 رقم اعشار

    current_nonce = nonce
    for i in range(repeats):
        try:
            print(f'   🔸 تکرار وارپ {i + 1}/{repeats}')
            receipt = send_transaction(
                to_address=config['contract'],
                value=value_in_wei,
                gas_limit=config['gas_limit'],
                data=config['method_id'],
                nonce=current_nonce
            )
            current_nonce += 1
        except Exception:
            print(f'   ❌ تکرار وارپ {i + 1} شکست خورد. ادامه به تکرار بعدی...')
        time.sleep(0.5) # تاخیر کوتاه
    return current_nonce

def execute_unstake(nonce):
    """اجرای تراکنش آن‌استیک."""
    print('\n--- 🔗 در حال اجرای تراکنش آن‌استیک ---')
    config = next((t for t in ALL_TRANSACTIONS if t['type'] == 'UNSTAKE'), None)
    if not config: return nonce

    amount_in_smallest_unit = to_smallest_unit(config['amount'], TOKEN_DECIMALS['INJ'])
    
    # ساخت فیلد data شامل Method ID و مقدار به عنوان پارامتر
    # Method ID + مقدار (پد شده به 32 بایت)
    data = config['method_id'] + w3.to_hex(amount_in_smallest_unit)[2:].zfill(64) # حذف '0x' و پد به 64 کاراکتر هگز

    try:
        receipt = send_transaction(
            to_address=config['contract'],
            value=0, # مقدار اصلی از طریق data ارسال می‌شود
            gas_limit=config['gas_limit'],
            data=data,
            nonce=nonce
        )
        return nonce + 1
    except Exception:
        print('❌ تراکنش آن‌استیک شکست خورد.')
        return nonce

def execute_swap_usdt_to_winj(nonce, run_time_key):
    """اجرای تراکنش سواپ USDT به wINJ و ذخیره خروجی."""
    print('\n--- 💰 در حال اجرای تراکنش سواپ USDT به wINJ ---')
    config = next((t for t in ALL_TRANSACTIONS if t['type'] == 'SWAP_USDT_TO_WINJ'), None)
    if not config: return nonce

    input_amount_wei = to_smallest_unit(config['input_amount'], TOKEN_DECIMALS['USDT'])
    min_amount_out_wei = to_smallest_unit(config['min_amount_out'], TOKEN_DECIMALS['SWAP_WINJ'])

    current_timestamp = int(time.time())
    deadline = current_timestamp + (60 * 10)  # 10 دقیقه از الان

    # بازسازی دقیق فیلد Data بر اساس نمونه شما
    # فرمت نمونه: MethodID + path[0] + path[1] + amountIn + to + deadline + minAmountOut + unknown1 + unknown2
    
    # پارامترهای پد شده (32 بایت = 64 کاراکتر هگز)
    method_id_padded = config['method_id'][2:] # حذف '0x'
    usdt_addr_padded = w3.to_hex(CONTRACT_ADDRESSES['USDT_TOKEN'])[2:].zfill(64)
    swap_winj_addr_padded = w3.to_hex(CONTRACT_ADDRESSES['SWAP_WINJ_TOKEN'])[2:].zfill(64)
    input_amount_padded = w3.to_hex(input_amount_wei)[2:].zfill(64)
    recipient_addr_padded = w3.to_hex(config['recipient'])[2:].zfill(64)
    deadline_padded = w3.to_hex(deadline)[2:].zfill(64)
    min_amount_out_padded = w3.to_hex(min_amount_out_wei)[2:].zfill(64)

    # پارامترهای ناشناس انتهایی از نمونه شما (ثابت)
    # اینها باید دقیقاً همان رشته‌های هگز از نمونه شما باشند.
    unknown_param1 = '00000000000000000000000000000000000000000000000000036861bb4b0c4b'
    unknown_param2 = '0000000000000000000000000000000000000000000000000000000000000000'

    full_data = '0x' + \
                method_id_padded + \
                usdt_addr_padded + \
                swap_winj_addr_padded + \
                input_amount_padded + \
                recipient_addr_padded + \
                deadline_padded + \
                min_amount_out_padded + \
                unknown_param1 + \
                unknown_param2
    
    try:
        receipt = send_transaction(
            to_address=config['contract'],
            value=0, # مقدار اصلی از طریق data ارسال می‌شود
            gas_limit=config['gas_limit'],
            data=full_data,
            nonce=nonce
        )

        # --- پس از موفقیت‌آمیز بودن تراکنش: دریافت مقدار wINJ دریافتی و ذخیره در فایل JSON ---
        winj_received = 0
        if receipt and receipt['logs']:
            # ABI مینیمال برای Transfer event
            transfer_event_abi = w3.eth.contract.events.get_event_abi("Transfer") # دریافت ABI استاندارد Transfer event

            for log in receipt['logs']:
                if log['address'].lower() == CONTRACT_ADDRESSES['SWAP_WINJ_TOKEN'].lower():
                    try:
                        # تلاش برای دیکد کردن لاگ Transfer
                        # وب3.پایتون خودش دیکد لاگ رو انجام میده
                        # نیاز به ساخت آبجکت Contract برای دیکد کردن لاگ Event هست
                        # یک تابع ساده برای بررسی topics و data کافیه
                        if len(log['topics']) == 3 and \
                           log['topics'][0] == Web3.keccak(text="Transfer(address,address,uint256)") and \
                           w3.to_checksum_address(log['topics'][2]) == to_checksum_address(config['recipient']):
                            
                            # مقدار value در data (پارامتر غیر ایندکس شده)
                            value_bytes = w3.to_int(log['data'])
                            winj_received = value_bytes
                            print(f'✨ دریافت شد: {from_smallest_unit(winj_received, TOKEN_DECIMALS["SWAP_WINJ"])} wINJ (سواپ)')
                            break # اولین لاگ Transfer مرتبط رو پیدا کردیم
                    except Exception as e:
                        print(f"⚠️ اخطار: خطا در دیکد کردن لاگ Transfer: {e}")
            
            if winj_received > 0:
                swap_outputs = read_swap_outputs()
                swap_outputs[run_time_key] = str(winj_received) # ذخیره به صورت رشته
                write_swap_outputs(swap_outputs)
            else:
                print('⚠️ اخطار: لاگ Transfer برای wINJ دریافتی پیدا نشد یا مقدار آن 0 است. مقدار 0 در فایل ذخیره می‌شود.')
        return nonce + 1
    except Exception:
        print('❌ تراکنش سواپ USDT به wINJ شکست خورد.')
        return nonce

def execute_swap_winj_to_usdt(nonce, run_time_key_for_input):
    """اجرای تراکنش سواپ wINJ به USDT با مقدار ورودی دینامیک."""
    print('\n--- 💸 در حال اجرای تراکنش سواپ wINJ به USDT ---')
    config = next((t for t in ALL_TRANSACTIONS if t['type'] == 'SWAP_WINJ_TO_USDT'), None)
    if not config: return nonce

    # خواندن مقدار wINJ از فایل JSON
    swap_outputs = read_swap_outputs()
    input_amount_winj_str = swap_outputs.get(run_time_key_for_input, "0")
    
    if not input_amount_winj_str or int(input_amount_winj_str) == 0:
        print(f'⚠️ اخطار: هیچ wINJ برای سواپ در زمان {run_time_key_for_input} پیدا نشد یا مقدار آن 0 است. تراکنش انجام نمی‌شود.')
        return nonce

    input_amount_winj = int(input_amount_winj_str) # تبدیل به عدد صحیح

    print(f'   🔸 سواپینگ {from_smallest_unit(input_amount_winj, TOKEN_DECIMALS["SWAP_WINJ"])} wINJ (سواپ) به USDT...')

    min_amount_out_wei = to_smallest_unit(config['min_amount_out'], TOKEN_DECIMALS['USDT'])
    current_timestamp = int(time.time())
    deadline = current_timestamp + (60 * 10)  # 10 دقیقه از الان

    # بازسازی دقیق فیلد Data بر اساس نمونه شما
    method_id_padded = config['method_id'][2:] # حذف '0x'
    winj_swap_addr_padded = w3.to_hex(CONTRACT_ADDRESSES['SWAP_WINJ_TOKEN'])[2:].zfill(64)
    usdt_addr_padded = w3.to_hex(CONTRACT_ADDRESSES['USDT_TOKEN'])[2:].zfill(64)
    input_amount_padded = w3.to_hex(input_amount_winj)[2:].zfill(64) # مقدار دینامیک
    recipient_addr_padded = w3.to_hex(config['recipient'])[2:].zfill(64)
    deadline_padded = w3.to_hex(deadline)[2:].zfill(64)
    min_amount_out_padded = w3.to_hex(min_amount_out_wei)[2:].zfill(64)

    # پارامترهای ناشناس انتهایی از نمونه شما (ثابت، همانند سواپ اول)
    unknown_param1 = '00000000000000000000000000000000000000000000000000036861bb4b0c4b'
    unknown_param2 = '0000000000000000000000000000000000000000000000000000000000000000'

    full_data = '0x' + \
                method_id_padded + \
                winj_swap_addr_padded + \
                usdt_addr_padded + \
                input_amount_padded + \
                recipient_addr_padded + \
                deadline_padded + \
                min_amount_out_padded + \
                unknown_param1 + \
                unknown_param2

    try:
        receipt = send_transaction(
            to_address=config['contract'],
            value=0,
            gas_limit=config['gas_limit'],
            data=full_data,
            nonce=nonce
        )
        return nonce + 1
    except Exception:
        print('❌ تراکنش سواپ wINJ به USDT شکست خورد.')
        return nonce

# --- 4. تابع اصلی اجرا (Main Execution Function) ---

async def main():
    try:
        current_nonce = w3.eth.get_transaction_count(SENDER_ADDRESS, 'pending')
        print(f'Current Nonce برای {SENDER_ADDRESS}: {current_nonce}')
    except Exception as e:
        print(f'❌ خطا در دریافت Nonce اولیه: {e}')
        exit(1)

    utc_now = datetime.now(pytz.utc)
    current_hour_utc = utc_now.hour
    current_minute_utc = utc_now.minute
    print(f'⏰ زمان فعلی UTC: {str(current_hour_utc).zfill(2)}:{str(current_minute_utc).zfill(2)}')

    for tx_config in ALL_TRANSACTIONS:
        should_run = False

        if IS_TEST_MODE:
            should_run = True
            print(f'\n--- 🧪 حالت تست فعال: اجرای فوری تراکنش "{tx_config["name"]}" ---')
        else:
            schedules = tx_config['schedule'] if isinstance(tx_config['schedule'], list) else [tx_config['schedule']]
            for schedule in schedules:
                # یک بازه 5 دقیقه‌ای برای شروع در نظر گرفته شده
                if current_hour_utc == schedule['hour'] and \
                   current_minute_utc >= schedule['minute'] and \
                   current_minute_utc < schedule['minute'] + 5:
                    should_run = True
                    break

        if should_run:
            print(f'\n--- ⏳ زمان اجرای تراکنش "{tx_config["name"]}" فرا رسیده است! ---')
            
            try:
                if tx_config['type'] == 'STAKE':
                    current_nonce = execute_stake(current_nonce)
                elif tx_config['type'] == 'WARP':
                    current_nonce = execute_warp(current_nonce, tx_config['repeats'])
                elif tx_config['type'] == 'UNSTAKE':
                    current_nonce = execute_unstake(current_nonce)
                elif tx_config['type'] == 'SWAP_USDT_TO_WINJ':
                    usdt_to_winj_run_time_key = f"{str(current_hour_utc).zfill(2)}:{str(current_minute_utc).zfill(2)}"
                    current_nonce = execute_swap_usdt_to_winj(current_nonce, usdt_to_winj_run_time_key)
                elif tx_config['type'] == 'SWAP_WINJ_TO_USDT':
                    input_key_for_winj_to_usdt = None
                    if current_hour_utc == 20 and current_minute_utc >= 0:
                        input_key_for_winj_to_usdt = '12:00'
                    elif current_hour_utc == 0 and current_minute_utc >= 0:
                        input_key_for_winj_to_usdt = '19:00'
                    elif IS_TEST_MODE: # در حالت تست، از خروجی 12:00 استفاده کن یا اولویت بده
                        print('⚠️ اخطار: در حالت تست، برای سواپ wINJ به USDT از خروجی 12:00 استفاده می‌شود.')
                        input_key_for_winj_to_usdt = '12:00'
                    else:
                        print(f'⚠️ اخطار: زمان اجرای نامشخص برای سواپ wINJ به USDT. ({current_hour_utc}:{current_minute_utc})')
                        continue # از اجرای این تراکنش صرف نظر می‌کنیم

                    current_nonce = execute_swap_winj_to_usdt(current_nonce, input_key_for_winj_to_usdt)
                else:
                    print(f'⚠️ اخطار: نوع تراکنش ناشناخته: {tx_config["type"]}')
            except Exception as e:
                print(f'❌ خطا در اجرای تراکنش "{tx_config["name"]}": {e}')
                # ادامه به تراکنش بعدی یا خروج بسته به نیاز
                # در اینجا ادامه می‌دهیم تا بقیه تراکنش‌ها هم بررسی شوند
        elif not IS_TEST_MODE: # اگر حالت تست نیست و اجرا نشد، پیغام بده
            print(f'\n--- ⏭️ تراکنش "{tx_config["name"]}" در حال حاضر اجرا نمی‌شود. ({str(current_hour_utc).zfill(2)}:{str(current_minute_utc).zfill(2)} UTC) ---')

    print('\n--- ✅ تمامی تراکنش‌های زمان‌بندی شده برای این اجرا بررسی شدند. ---')

# اجرای تابع اصلی (به صورت ناهمزمان)
if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
