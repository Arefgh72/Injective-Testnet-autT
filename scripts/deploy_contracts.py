# scripts/deploy_contracts.py

import os
import json
import time
import random
from web3 import Web3, HTTPProvider
from eth_account import Account
from eth_utils import to_checksum_address, decode_hex, encode_hex
from solcx import compile_standard, install_solc, set_solc_version, get_installed_solc_versions, get_solc_version # استفاده از compile_standard

# --- 1. تنظیمات (Configuration) ---

# کلید خصوصی از متغیرهای محیطی GitHub Secret خوانده می‌شود
# تغییر نام Secret به INJECTIVE_PRIVATE_KEY
PRIVATE_KEY = os.environ.get('INJECTIVE_PRIVATE_KEY') 
if not PRIVATE_KEY:
    print('خطا: متغیر محیطی INJECTIVE_PRIVATE_KEY تنظیم نشده است.')
    exit(1)
if not PRIVATE_KEY.startswith("0x"):
    PRIVATE_KEY = "0x" + PRIVATE_KEY

# تنظیمات RPC و Chain ID برای Injective Testnet
RPC_URL = "https://k8s.testnet.json-rpc.injective.network/" # RPC صحیح Injective
CHAIN_ID = 1439 # Chain ID صحیح Injective
EXPLORER_URL_TX_FORMAT = "https://testnet.blockscout.injective.network/tx/{}" # اکسپلورر Injective

# تنظیمات Web3
web3_provider = HTTPProvider(
    RPC_URL,
    request_kwargs={
        'timeout': 60,  # افزایش زمان timeout به 60 ثانیه
        'verify': True, # بررسی گواهینامه‌های SSL
        'proxies': None # اطمینان از عدم استفاده از پراکسی
    }
)
w3 = Web3(web3_provider)

if not w3.is_connected():
    print(f'خطا: اتصال به RPC Endpoint {RPC_URL} برقرار نشد.')
    exit(1)
print(f'✅ اتصال به شبکه {RPC_URL} برقرار شد.')

account = Account.from_key(PRIVATE_KEY)
SENDER_ADDRESS = to_checksum_address(account.address)
print(f'✅ آدرس کیف پول فرستنده: {SENDER_ADDRESS}')

# Gas Price ثابت (می‌تونید از w3.eth.gas_price هم استفاده کنید برای دینامیک)
FIXED_GAS_PRICE_WEI = w3.to_wei('0.192', 'gwei')

# Gas Limits برای دیپلوی
DEPLOY_GAS_LIMIT_SIMPLE_STORAGE = 2000000 # گس لیمیت برای SimpleStorage
DEPLOY_GAS_LIMIT_MY_NFT = 6000000 # گس لیمیت برای MyNFT (معمولا NFT ها گس بیشتری نیاز دارن)

# --- 2. توابع کمکی (Helper Functions) ---

async def send_transaction(to_address, value, gas_limit, data, retries=10, delay=15):
    """ارسال یک تراکنش امضا شده با قابلیت تلاش مجدد."""
    for attempt in range(retries):
        current_nonce = w3.eth.get_transaction_count(SENDER_ADDRESS, 'pending')
        print(f"   (دریافت Nonce لحظه‌ای برای تلاش {attempt + 1}/{retries}: {current_nonce})")

        try:
            transaction = {
                'from': SENDER_ADDRESS,
                'to': to_checksum_address(to_address) if to_address else None, # None برای دیپلوی قرارداد
                'value': value,
                'gas': gas_limit,
                'gasPrice': FIXED_GAS_PRICE_WEI,
                'nonce': current_nonce,
                'chainId': CHAIN_ID,
                'data': data
            }
            
            signed_transaction = account.sign_transaction(transaction)
            
            print(f'🚀 در حال ارسال تراکنش دیپلوی به: {to_address if to_address else "شبکه (دیپلوی)"}، Nonce: {current_nonce}، Gas: {gas_limit} (تلاش {attempt + 1}/{retries})')
            
            tx_hash = w3.eth.send_raw_transaction(signed_transaction.rawTransaction)
            print(f"  تراکنش ارسال شد. هش: {encode_hex(tx_hash)}")
            
            tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300) # افزایش زمان انتظار
            
            if tx_receipt.status == 1:
                print(f'✅ تراکنش موفق! هش: {encode_hex(tx_receipt.transactionHash)}, آدرس قرارداد: {tx_receipt.contractAddress}')
                if tx_receipt.contractAddress: # اگر قرارداد دیپلوی شده باشد
                    print(f"  مشاهده در اکسپلورر: {EXPLORER_URL_TX_FORMAT.format(encode_hex(tx_receipt.transactionHash))}")
                return tx_receipt
            else:
                print(f'❌ تراکنش رد شد. هش: {encode_hex(tx_receipt.transactionHash)}, وضعیت: {tx_receipt.status}')
                raise Exception(f"تراکنش با وضعیت {tx_receipt.status} شکست خورد.")

        except Exception as e:
            error_message = str(e)
            print(f'🚨 خطا در ارسال تراکنش دیپلوی (Nonce: {current_nonce}, تلاش {attempt + 1}/{retries}): {error_message}')
            
            if "invalid nonce" in error_message or "mempool is full" in error_message or "503" in error_message or "Service Temporarily Unavailable" in error_message or "nonce too low" in error_message or "already known" in error_message or "connection" in error_message.lower() or "timed out" in error_message.lower():
                print(f"   تلاش مجدد در {delay} ثانیه...")
                time.sleep(delay)
            else:
                print("   خطای غیرقابل حل با تلاش مجدد. توقف.")
                raise 
    
    raise Exception(f"تراکنش دیپلوی بعد از {retries} تلاش ناموفق بود.")


def compile_contract(contract_name, contract_path, base_path):
    """کامپایل یک فایل Solidity و بازگرداندن ABI و Bytecode."""
    print(f"\n--- در حال کامپایل {contract_name}.sol ---")
    
    with open(contract_path, 'r') as f:
        source_code = f.read()

    # کامپایل استاندارد Solidity
    # allow_paths به solc اجازه میده فایل‌های import شده رو در base_path پیدا کنه
    compiled_sol = compile_standard(
        {
            "language": "Solidity",
            "sources": {
                contract_path: {"content": source_code} # اینجا از مسیر کامل فایل استفاده می‌کنیم
            },
            "settings": {
                "outputSelection": {
                    "*": {
                        "*": ["abi", "evm.bytecode"]
                    }
                }
            }
        },
        solc_version="0.8.20", 
        allow_paths=[base_path] # base_path رو به دایرکتوری که import ها توشن میدیم
    )
    
    # استخراج ABI و Bytecode
    # نام فایل در 'contracts' و نام قرارداد در 'compiled_sol['contracts'][file_name][contract_name]'
    bytecode = compiled_sol['contracts'][contract_path][contract_name]['evm']['bytecode']['object']
    abi = compiled_sol['contracts'][contract_path][contract_name]['abi']
    
    print(f"✅ {contract_name}.sol با موفقیت کامپایل شد.")
    return bytecode, abi

# --- 3. تابع اصلی دیپلوی ---

async def main():
    print('--- شروع فرآیند دیپلوی قراردادها ---')

    # نصب کامپایلر solc (فقط یک بار در شروع)
    print("در حال بررسی و نصب کامپایلر solc...")
    try:
        if get_installed_solc_versions():
            print(f"solc {get_solc_version()} از قبل نصب شده است.")
        else:
            install_solc('0.8.20')
            print("solc 0.8.20 با موفقیت نصب شد.")
        set_solc_version('0.8.20') 
    except Exception as e:
        print(f"🚨 خطا در نصب یا تنظیم solc: {e}")
        exit(1)

    # مسیر ریشه پروژه (یک دایرکتوری بالاتر از scripts)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
    contracts_dir = os.path.join(project_root, "contracts")

    # کامپایل SimpleStorage
    simple_storage_bytecode, simple_storage_abi = compile_contract(
        "SimpleStorage", 
        os.path.join(contracts_dir, "SimpleStorage.sol"),
        base_path=contracts_dir # base_path رو به دایرکتوری contracts میدیم
    )
    
    # کامپایل MyNFT (اگر نیاز به OpenZeppelin باشه، باید node_modules هم نصب بشه)
    # OpenZeppelin Contracts معمولاً در node_modules نصب می‌شوند
    # اگر از npm install @openzeppelin/contracts استفاده شود، باید base_path شامل node_modules باشد.
    # در اینجا، فرض بر این است که قراردادهای OpenZeppelin نیز در همین contracts_dir قرار دارند.
    # اگر اینطور نیست و خطا داد، باید مرحله npm install رو به Workflow اضافه کنیم.
    my_nft_bytecode, my_nft_abi = compile_contract(
        "MyNFT", 
        os.path.join(contracts_dir, "MyNFT.sol"), 
        base_path=contracts_dir # base_path رو به دایرکتوری contracts میدیم
    )

    # دیپلوی 10 بار از هر قرارداد
    num_deploys = 10

    print(f"\n--- در حال دیپلوی {num_deploys} قرارداد SimpleStorage ---")
    for i in range(num_deploys):
        print(f"دیپلوی SimpleStorage {i+1}/{num_deploys}")
        try:
            receipt = await send_transaction(
                to_address=None, # برای دیپلوی قرارداد
                value=0,
                gas_limit=DEPLOY_GAS_LIMIT_SIMPLE_STORAGE,
                data=simple_storage_bytecode,
            )
            time.sleep(15) # تاخیر بین دیپلوی‌ها
        except Exception as e:
            print(f"❌ دیپلوی SimpleStorage {i+1} شکست خورد: {e}")
            time.sleep(5) # تاخیر در صورت شکست

    print(f"\n--- در حال دیپلوی {num_deploys} قرارداد MyNFT ---")
    for i in range(num_deploys):
        print(f"دیپلوی MyNFT {i+1}/{num_deploys}")
        try:
            receipt = await send_transaction(
                to_address=None, # برای دیپلوی قرارداد
                value=0,
                gas_limit=DEPLOY_GAS_LIMIT_MY_NFT,
                data=my_nft_bytecode,
            )
            time.sleep(15) # تاخیر بین دیپلوی‌ها
        except Exception as e:
            print(f"❌ دیپلوی MyNFT {i+1} شکست خورد: {e}")
            time.sleep(5) # تاخیر در صورت شکست

    print('\n--- فرآیند دیپلوی قراردادها به پایان رسید. ---')

# اجرای تابع اصلی
if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
