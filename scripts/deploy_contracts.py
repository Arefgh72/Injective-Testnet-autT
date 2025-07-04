# scripts/deploy_contracts.py

import os
import json
import time
import random
import subprocess # برای اجرای دستورات سیستمی
from web3 import Web3, HTTPProvider
from eth_account import Account
from eth_utils import to_checksum_address, decode_hex, encode_hex

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
            
            tx_hash = w3.eth.send_raw_transaction(signed_transaction.rawTransaction) # تغییر t کوچک به T بزرگ
            print(f"  تراکنش ارسال شد. هش: {encode_hex(tx_hash)}")
            
            tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            if tx_receipt.status == 1:
                print(f'✅ تراکنش موفق! هش: {encode_hex(tx_receipt.transactionHash)}, آدرس قرارداد: {tx_receipt.contractAddress}')
                if tx_receipt.contractAddress:
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


def compile_contract(contract_name, contract_path, contracts_base_path, project_root):
    """کامپایل یک فایل Solidity با استفاده از solc به صورت subprocess."""
    print(f"\n--- در حال کامپایل {contract_name}.sol با solc مستقیم ---")
    
    output_dir = os.path.dirname(contract_path)
    
    # مسیر node_modules برای OpenZeppelin
    node_modules_path = os.path.join(project_root, "node_modules")

    try:
        command = [
            "solc",
            "--base-path", contracts_base_path, # مسیر پایه برای import های معمولی (مثلاً همین دایرکتوری contracts)
            "--include-path", node_modules_path, # **مهم:** مسیر node_modules برای import های OpenZeppelin
            "--bin",
            "--abi",
            "--overwrite",
            "--output-dir", output_dir,
            contract_path # فایل قراردادی که قرار است کامپایل شود
        ]
        
        # اجرای دستور solc
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print("Solc Output (stdout):\n", result.stdout)
        if result.stderr:
            print("Solc Errors (stderr):\n", result.stderr)

        # خواندن ABI و Bytecode از فایل‌های تولید شده
        abi_file_path = os.path.join(output_dir, f"{contract_name}.abi")
        bin_file_path = os.path.join(output_dir, f"{contract_name}.bin")

        with open(abi_file_path, 'r') as f:
            abi = json.load(f)
        with open(bin_file_path, 'r') as f:
            bytecode = f.read().strip()

        print(f"✅ {contract_name}.sol با موفقیت کامپایل شد و ABI/Bytecode از فایل‌ها خوانده شد.")
        return bytecode, abi
    except subprocess.CalledProcessError as e:
        print(f"🚨 خطا در اجرای solc برای {contract_name}.sol: {e}")
        print(f"Solc stdout: {e.stdout}")
        print(f"Solc stderr: {e.stderr}")
        raise
    except FileNotFoundError:
        print("🚨 خطا: دستور 'solc' پیدا نشد. مطمئن شوید solc نصب و در PATH سیستم است.")
        raise
    except Exception as e:
        print(f"🚨 خطای ناشناخته در کامپایل {contract_name}.sol: {e}")
        raise

# --- 3. تابع اصلی دیپلوی ---

async def main():
    print('--- شروع فرآیند دیپلوی قراردادها ---')

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
    contracts_dir = os.path.join(project_root, "contracts")

    # کامپایل SimpleStorage
    simple_storage_bytecode, simple_storage_abi = compile_contract(
        "SimpleStorage", 
        os.path.join(contracts_dir, "SimpleStorage.sol"),
        contracts_base_path=contracts_dir, # base_path رو به دایرکتوری contracts میدیم
        project_root=project_root 
    )
    
    # کامپایل MyNFT
    my_nft_bytecode, my_nft_abi = compile_contract(
        "MyNFT", 
        os.path.join(contracts_dir, "MyNFT.sol"), 
        contracts_base_path=contracts_dir, # base_path رو به دایرکتوری contracts میدیم
        project_root=project_root 
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
