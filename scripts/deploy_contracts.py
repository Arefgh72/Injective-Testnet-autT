# scripts/deploy_contracts.py

import os
import json
import time
import random
from web3 import Web3, HTTPProvider
from eth_account import Account
from eth_utils import to_checksum_address, decode_hex, encode_hex
# تغییر در Import کامپایلر: استفاده از pysolcx
from pysolcx import compile_solc, install_solc, get_solc_version, set_solc_version, get_installed_solc_versions

# --- 1. تنظیمات (Configuration) ---

PRIVATE_KEY = os.environ.get('INJECTIVE_PRIVATE_KEY')
if not PRIVATE_KEY:
    print('خطا: متغیر محیطی INJECTIVE_PRIVATE_KEY تنظیم نشده است.')
    exit(1)
if not PRIVATE_KEY.startswith("0x"):
    PRIVATE_KEY = "0x" + PRIVATE_KEY

RPC_URL = "https://k8s.testnet.json-rpc.injective.network/" 
CHAIN_ID = 1439 

# تنظیمات Web3
web3_provider = HTTPProvider(
    RPC_URL,
    request_kwargs={
        'timeout': 60,
        'verify': True,
        'proxies': None
    }
)
w3 = Web3(web3_provider)

try:
    if not w3.is_connected():
        print(f'خطا: اتصال به RPC Endpoint {RPC_URL} برقرار نشد.')
        exit(1)
    print(f'اتصال به شبکه {RPC_URL} برقرار شد.')
except Exception as e:
    print(f'خطا در برقراری اتصال اولیه به RPC Endpoint {RPC_URL}: {e}')
    exit(1)

account = Account.from_key(PRIVATE_KEY)
SENDER_ADDRESS = to_checksum_address(account.address)
print(f'آدرس کیف پول فرستنده: {SENDER_ADDRESS}')

FIXED_GAS_PRICE_WEI = w3.to_wei('0.192', 'gwei')

DEPLOY_GAS_LIMIT_SIMPLE_STORAGE = 2000000 
DEPLOY_GAS_LIMIT_MY_NFT = 6000000 

# --- 2. توابع کمکی (Helper Functions) ---

async def send_transaction(to_address, value, gas_limit, data, retries=10, delay=15):
    """ارسال یک تراکنش امضا شده با قابلیت تلاش مجدد."""
    for attempt in range(retries):
        current_nonce = w3.eth.get_transaction_count(SENDER_ADDRESS, 'pending')
        print(f"   (دریافت Nonce لحظه‌ای برای تلاش {attempt + 1}/{retries}: {current_nonce})")

        try:
            transaction = {
                'from': SENDER_ADDRESS,
                'to': to_checksum_address(to_address) if to_address else None,
                'value': value,
                'gas': gas_limit,
                'gasPrice': FIXED_GAS_PRICE_WEI,
                'nonce': current_nonce,
                'chainId': CHAIN_ID,
                'data': data
            }
            
            signed_transaction = account.sign_transaction(transaction)
            
            print(f'🚀 در حال ارسال تراکنش دیپلوی به: {to_address if to_address else "شبکه (دیپلوی)"}، Nonce: {current_nonce}، Gas: {gas_limit} (تلاش {attempt + 1}/{retries})')
            
            tx_hash = w3.eth.send_raw_transaction(signed_transaction.raw_transaction)
            print(f"  تراکنش ارسال شد. هش: {encode_hex(tx_hash)}")
            
            tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            if tx_receipt.status == 1:
                print(f'✅ تراکنش موفق! هش: {encode_hex(tx_receipt.transactionHash)}, آدرس قرارداد: {tx_receipt.contractAddress}')
                if tx_receipt.contractAddress:
                    # EXPLORER_URL_TX_FORMAT رو در اینجا تعریف نکرده بودیم
                    explorer_url_tx_format = "https://testnet.blockscout.injective.network/tx/{}"
                    print(f"  مشاهده در اکسپلورر: {explorer_url_tx_format.format(encode_hex(tx_receipt.transactionHash))}")
                return tx_receipt
            else:
                print(f'❌ تراکنش رد شد. هش: {encode_hex(tx_receipt.transactionHash)}, وضعیت: {tx_receipt.status}')
                raise Exception(f"تراکنش با وضعیت {tx_receipt.status} شکست خورد.")

        except Exception as e:
            error_message = str(e)
            print(f'🚨 خطا در ارسال تراکنش دیپلوی (Nonce: {current_nonce}, تلاش {attempt + 1}/{retries}): {error_message}')
            
            if "invalid nonce" in error_message or "mempool is full" in error_message or "503" in error_message or "Service Temporarily Unavailable" in error_message or "nonce too low" in error_message or "already known" in error_message or "connection" in error_message.lower() or "timed out" in error_message.lower() or "gas required exceeds allowance" in error_message.lower():
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

    # استفاده از compile_solc از pysolcx
    # allow_paths برای پیدا کردن import ها
    compiled_sol = compile_solc(
        source_code,
        solc_version="0.8.20",
        base_path=base_path, # base_path رو به دایرکتوری که import ها توشن میدیم
        output_values=["abi", "bin"]
    )
    
    # استخراج ABI و Bytecode (نحوه دسترسی به خروجی در pysolcx کمی متفاوته)
    # خروجی مستقیماً شامل نام فایل و نام قرارداد است
    # مثال: {'<stdin>': {'SimpleStorage': {'abi': [...], 'bin': '...'}}}
    # اگر از compile_files استفاده میکردید، خروجی به شکل {'file.sol:ContractName': {...}} بود.
    # برای سازگاری با compile_files که قبلاً توی نمونه‌تون بود:
    contract_key = f"{os.path.basename(contract_path)}:{contract_name}"
    
    bytecode = compiled_sol[contract_key]['bin']
    abi = compiled_sol[contract_key]['abi']
    
    print(f"✅ {contract_name}.sol با موفقیت کامپایل شد.")
    return bytecode, abi

# --- 3. تابع اصلی دیپلوی ---

async def main():
    print('--- شروع فرآیند دیپلوی قراردادها ---')

    print("در حال بررسی و نصب کامپایلر solc (از طریق pysolcx)...")
    try:
        # pysolcx خودش میتونه solc رو دانلود و نصب کنه.
        # ابتدا چک میکنیم نسخه 0.8.20 نصب شده یا نه.
        installed_versions = get_installed_solc_versions()
        if "v0.8.20" not in [str(v) for v in installed_versions]:
            install_solc('0.8.20')
            print("solc 0.8.20 با موفقیت نصب شد.")
        else:
            print(f"solc {get_solc_version()} از قبل نصب شده است.")
        set_solc_version('0.8.20') 
    except Exception as e:
        print(f"🚨 خطا در نصب یا تنظیم solc: {e}")
        exit(1)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
    contracts_dir = os.path.join(project_root, "contracts")

    # کامپایل SimpleStorage
    simple_storage_bytecode, simple_storage_abi = compile_contract(
        "SimpleStorage", 
        os.path.join(contracts_dir, "SimpleStorage.sol"),
        base_path=contracts_dir 
    )
    
    # کامپایل MyNFT
    my_nft_bytecode, my_nft_abi = compile_contract(
        "MyNFT", 
        os.path.join(contracts_dir, "MyNFT.sol"), 
        base_path=contracts_dir 
    )

    num_deploys = 10

    print(f"\n--- در حال دیپلوی {num_deploys} قرارداد SimpleStorage ---")
    for i in range(num_deploys):
        print(f"دیپلوی SimpleStorage {i+1}/{num_deploys}")
        try:
            receipt = await send_transaction(
                to_address=None,
                value=0,
                gas_limit=DEPLOY_GAS_LIMIT_SIMPLE_STORAGE,
                data=simple_storage_bytecode,
            )
            time.sleep(15) 
        except Exception as e:
            print(f"❌ دیپلوی SimpleStorage {i+1} شکست خورد: {e}")
            time.sleep(5) 

    print(f"\n--- در حال دیپلوی {num_deploys} قرارداد MyNFT ---")
    for i in range(num_deploys):
        print(f"دیپلوی MyNFT {i+1}/{num_deploys}")
        try:
            receipt = await send_transaction(
                to_address=None,
                value=0,
                gas_limit=DEPLOY_GAS_LIMIT_MY_NFT,
                data=my_nft_bytecode,
            )
            time.sleep(15) 
        except Exception as e:
            print(f"❌ دیپلوی MyNFT {i+1} شکست خورد: {e}")
            time.sleep(5) 

    print('\n--- فرآیند دیپلوی قراردادها به پایان رسید. ---')

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
