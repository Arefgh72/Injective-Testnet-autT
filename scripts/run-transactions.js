// scripts/run-transactions.js

const Web3 = require('web3');
const { TransactionFactory } = require('@ethereumjs/tx');
const { hexToBytes, bytesToHex } = require('@ethereumjs/util');
const Common = require('@ethereumjs/common').default;
const fs = require('fs-extra'); // For async file operations like read/write JSON

// --- 1. تنظیمات (Configuration) ---

// کلید خصوصی از GitHub Secret خوانده می‌شود
const PRIVATE_KEY = process.env.INJECTIVE_PRIVATE_KEY;
if (!PRIVATE_KEY) {
  console.error('❌ خطا: متغیر محیطی INJECTIVE_PRIVATE_KEY تنظیم نشده است.');
  process.exit(1);
}

// تبدیل کلید خصوصی به بایت
const privateKeyBytes = hexToBytes(PRIVATE_KEY.startsWith('0x') ? PRIVATE_KEY : '0x' + PRIVATE_KEY);

// اطلاعات شبکه Injective Testnet
const RPC_URL = 'https://k8s.testnet.json-rpc.injective.network/';
const CHAIN_ID = 1439; // Chain ID تست‌نت Injective

// تنظیمات Web3
const web3 = new Web3(RPC_URL);
const common = Common.custom({ chainId: CHAIN_ID });

// آدرس فرستنده (کیف پول شما) که از کلید خصوصی مشتق می‌شود
const SENDER_ACCOUNT = web3.eth.accounts.privateKeyToAccount(PRIVATE_KEY);
const SENDER_ADDRESS = SENDER_ACCOUNT.address;
console.log(`✅ آدرس کیف پول فرستنده: ${SENDER_ADDRESS}`);

// آدرس قراردادها و توکن‌ها
const CONTRACT_ADDRESSES = {
  STAKING: '0x494401396FD1cf51cDD13e29eCFA769F49e1F5D3',
  WARP_UNWARP_WINJ: '0x5Ae9B425f58B78e0d5e7e5a7A75c5f5B45d143B7', // wINJ برای وارپ/آن‌وارپ
  DEX_BSWAP: '0x822f872763B7Be16c9b9687D8b9D73f1b5017Df0',
  USDT_TOKEN: '0x719ff496dDF37c56f2a958676F630f417A4084Aa', // USDT در تست‌نت (6 رقم اعشار)
  SWAP_WINJ_TOKEN: '0xE1C64dDE0A990AC2435B05Dcdac869A17FE06BD2', // wINJ در DEX (18 رقم اعشار)
};

// تعداد ارقام اعشار برای هر توکن
const TOKEN_DECIMALS = {
  INJ: 18,
  USDT: 6,
  SWAP_WINJ: 18,
};

// قیمت و گس لیمیت ثابت (بر اساس نمونه‌های ارسالی شما)
const FIXED_GAS_PRICE_WEI = '0xb71b000'; // تقریباً 0.192 Gwei

const GAS_LIMITS = {
  STAKE: '0x4ed698', // 5297304
  WARP: '0xcd8b',    // 52619
  UNSTAKE: '0x650edd', // 6623965
  SWAP: '0xa0983',     // 657795
};

// مسیر فایل برای ذخیره خروجی سواپ‌های دینامیک
const SWAP_OUTPUTS_FILE = 'data/swap-outputs.json';

// پیکربندی تمام تراکنش‌ها با زمان‌بندی و جزئیات
const ALL_TRANSACTIONS = [
  {
    name: 'استیک (Stake)',
    type: 'STAKE',
    contract: CONTRACT_ADDRESSES.STAKING,
    methodId: '0x8aa2799c',
    value: '0.1', // 0.1 INJ
    repeats: 1,
    gasLimit: GAS_LIMITS.STAKE,
    schedule: { hour: 5, minute: 30 }, // 05:30 UTC
  },
  {
    name: 'وارپ (Warp)',
    type: 'WARP',
    contract: CONTRACT_ADDRESSES.WARP_UNWARP_WINJ,
    methodId: '0xd0e30db0', // deposit()
    value: '0.001', // 0.001 INJ
    repeats: 50,
    gasLimit: GAS_LIMITS.WARP,
    schedule: [
      { hour: 6, minute: 0 },
      { hour: 9, minute: 0 },
      { hour: 14, minute: 0 },
      { hour: 18, minute: 0 },
      { hour: 23, minute: 0 },
    ],
  },
  {
    name: 'آن‌استیک (Unstake)',
    type: 'UNSTAKE',
    contract: CONTRACT_ADDRESSES.STAKING,
    methodId: '0xc9107def',
    amount: '0.09', // 0.09 INJ (as parameter in data)
    repeats: 1,
    gasLimit: GAS_LIMITS.UNSTAKE,
    schedule: { hour: 14, minute: 10 }, // 14:10 UTC
  },
  {
    name: 'سواپ USDT به wINJ',
    type: 'SWAP_USDT_TO_WINJ',
    contract: CONTRACT_ADDRESSES.DEX_BSWAP,
    methodId: '0x414bf389',
    inputAmount: '0.01', // 0.01 USDT
    inputTokenAddress: CONTRACT_ADDRESSES.USDT_TOKEN,
    outputTokenAddress: CONTRACT_ADDRESSES.SWAP_WINJ_TOKEN,
    // minAmountOut: برای تست‌نت، مقدار خیلی کمی در نظر می‌گیریم تا تراکنش رد نشه
    minAmountOut: '1', // 1 wei of wINJ
    recipient: SENDER_ADDRESS,
    repeats: 1,
    gasLimit: GAS_LIMITS.SWAP,
    schedule: [
      { hour: 12, minute: 0 },
      { hour: 19, minute: 0 },
    ],
  },
  {
    name: 'سواپ wINJ به USDT',
    type: 'SWAP_WINJ_TO_USDT',
    contract: CONTRACT_ADDRESSES.DEX_BSWAP,
    methodId: '0x414bf389',
    inputTokenAddress: CONTRACT_ADDRESSES.SWAP_WINJ_TOKEN,
    outputTokenAddress: CONTRACT_ADDRESSES.USDT_TOKEN,
    // minAmountOut: برای تست‌نت، مقدار خیلی کمی در نظر می‌گیریم
    minAmountOut: '1', // 1 wei of USDT
    recipient: SENDER_ADDRESS,
    repeats: 1,
    gasLimit: GAS_LIMITS.SWAP,
    schedule: [
      { hour: 20, minute: 0 },
      { hour: 0, minute: 0 }, // 24:00 UTC
    ],
  },
];

// --- 2. توابع کمکی (Helper Functions) ---

/**
 * تبدیل مقدار توکن خوانا به کوچکترین واحد (مثل wei) بر اساس اعشار
 * @param {string} amount - مقدار توکن (مثلاً "0.01")
 * @param {number} decimals - تعداد اعشار توکن (مثلاً 18 برای INJ)
 * @returns {string} مقدار در کوچکترین واحد (به صورت رشته)
 */
function toSmallestUnit(amount, decimals) {
  const [integerPart, decimalPart = ''] = amount.split('.');
  const paddedDecimalPart = decimalPart.padEnd(decimals, '0');
  if (paddedDecimalPart.length > decimals) {
      // If the original amount had more decimals than the token supports, truncate it
      console.warn(`⚠️ هشدار: مقدار ${amount} دارای اعشار بیشتری از ${decimals} است. قسمت‌های اضافی بریده می‌شوند.`);
  }
  const fullAmount = integerPart + paddedDecimalPart.substring(0, decimals);
  return BigInt(fullAmount).toString();
}

/**
 * تبدیل مقدار از کوچکترین واحد (مثل wei) به فرمت خوانا
 * @param {string} amountInSmallestUnit - مقدار در کوچکترین واحد (به صورت رشته)
 * @param {number} decimals - تعداد اعشار توکن
 * @returns {string} مقدار به صورت خوانا
 */
function fromSmallestUnit(amountInSmallestUnit, decimals) {
  const bn = BigInt(amountInSmallestUnit);
  const divisor = 10n ** BigInt(decimals);
  const integerPart = bn / divisor;
  let decimalPart = bn % divisor;

  if (decimalPart === 0n) {
    return integerPart.toString();
  }

  let decimalString = decimalPart.toString().padStart(decimals, '0');
  decimalString = decimalString.replace(/0+$/, ''); // حذف صفرهای اضافی انتهایی

  return `${integerPart.toString()}.${decimalString}`;
}

/**
 * خواندن خروجی‌های سواپ از فایل JSON
 * @returns {Promise<object>} داده‌های خروجی سواپ
 */
async function readSwapOutputs() {
  try {
    if (!await fs.pathExists(SWAP_OUTPUTS_FILE)) {
      console.log(`ℹ️ فایل ${SWAP_OUTPUTS_FILE} وجود ندارد، در حال ایجاد فایل جدید...`);
      // مقادیر پیش‌فرض را با 0 (در کوچکترین واحد) مقداردهی اولیه می‌کنیم
      await fs.outputJson(SWAP_OUTPUTS_FILE, {
        "12:00": "0", // مقدار wINJ از سواپ ساعت 12:00 UTC
        "19:00": "0"  // مقدار wINJ از سواپ ساعت 19:00 UTC
      }, { spaces: 2 });
    }
    return await fs.readJson(SWAP_OUTPUTS_FILE);
  } catch (error) {
    console.error(`❌ خطا در خواندن فایل ${SWAP_OUTPUTS_FILE}:`, error.message);
    return { "12:00": "0", "19:00": "0" }; // بازگرداندن مقادیر پیش‌فرض در صورت خطا
  }
}

/**
 * نوشتن خروجی‌های سواپ در فایل JSON
 * @param {object} data - داده‌های خروجی سواپ برای نوشتن
 */
async function writeSwapOutputs(data) {
  try {
    await fs.outputJson(SWAP_OUTPUTS_FILE, data, { spaces: 2 });
    console.log(`✅ فایل ${SWAP_OUTPUTS_FILE} به‌روزرسانی شد.`);
  } catch (error) {
    console.error(`❌ خطا در نوشتن در فایل ${SWAP_OUTPUTS_FILE}:`, error.message);
  }
}

/**
 * ارسال یک تراکنش امضا شده (Raw Transaction)
 * @param {object} txObject - آبجکت تراکنش برای امضا و ارسال.
 * @param {number} currentNonce - Nonce فعلی برای این تراکنش.
 * @returns {Promise<object>} رسید تراکنش (transaction receipt).
 */
async function sendTransaction(txObject, currentNonce) {
  try {
    const txData = {
      ...txObject,
      nonce: currentNonce,
      gasPrice: FIXED_GAS_PRICE_WEI, // استفاده از گس پرایس ثابت
      chainId: CHAIN_ID,
    };

    // ساخت تراکنش با EthereumJS Tx
    const tx = TransactionFactory.fromTxData(txData, { common });
    const signedTx = tx.sign(privateKeyBytes);
    const serializedTx = bytesToHex(signedTx.serialize());

    console.log(`🚀 در حال ارسال تراکنش به: ${txObject.to}، Nonce: ${currentNonce}، Value: ${txObject.value ? fromSmallestUnit(txObject.value, TOKEN_DECIMALS.INJ) : '0'} INJ`);
    const receipt = await web3.eth.sendSignedTransaction(serializedTx);
    console.log(`✅ تراکنش موفق! هش: ${receipt.transactionHash}`);
    return receipt;
  } catch (error) {
    console.error(`❌ خطا در ارسال تراکنش به ${txObject.to} (Nonce: ${currentNonce}):`, error.message);
    throw error; // خطا را به حلقه اصلی برمی‌گردانیم
  }
}

/**
 * دریافت موجودی توکن ERC20
 * @param {string} tokenAddress - آدرس قرارداد توکن
 * @param {string} ownerAddress - آدرس ولت
 * @returns {Promise<string>} موجودی توکن در کوچکترین واحد
 */
async function getERC20Balance(tokenAddress, ownerAddress) {
  const tokenContract = new web3.eth.Contract(
    // ABI مینیمال برای تابع balanceOf
    [{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"}],
    tokenAddress
  );
  try {
    const balance = await tokenContract.methods.balanceOf(ownerAddress).call();
    return balance.toString();
  } catch (error) {
    console.error(`❌ خطا در دریافت موجودی توکن ${tokenAddress} برای ${ownerAddress}:`, error.message);
    return '0';
  }
}

// --- 3. توابع اجرای تراکنش‌های خاص ---

/**
 * اجرای تراکنش استیک
 * @param {number} nonce - Nonce فعلی
 * @returns {Promise<number>} Nonce جدید
 */
async function executeStake(nonce) {
  console.log('\n--- 🥩 در حال اجرای تراکنش استیک ---');
  const config = ALL_TRANSACTIONS.find(t => t.type === 'STAKE');
  const valueInWei = toSmallestUnit(config.value, TOKEN_DECIMALS.INJ);

  const txObject = {
    to: config.contract,
    value: valueInWei,
    gasLimit: config.gasLimit,
    data: config.methodId,
  };

  try {
    await sendTransaction(txObject, nonce);
    return nonce + 1;
  } catch (error) {
    console.error('❌ تراکنش استیک شکست خورد.');
    return nonce; // در صورت شکست، Nonce را افزایش نمی‌دهیم
  }
}

/**
 * اجرای تراکنش وارپ
 * @param {number} nonce - Nonce فعلی
 * @param {number} repeats - تعداد تکرار
 * @returns {Promise<number>} Nonce جدید
 */
async function executeWarp(nonce, repeats) {
  console.log(`\n--- 🔄 در حال اجرای تراکنش وارپ (${repeats} بار) ---`);
  const config = ALL_TRANSACTIONS.find(t => t.type === 'WARP');
  const valueInWei = toSmallestUnit(config.value, TOKEN_DECIMALS.INJ);

  const txObject = {
    to: config.contract,
    value: valueInWei,
    gasLimit: config.gasLimit,
    data: config.methodId,
  };

  let currentNonce = nonce;
  for (let i = 0; i < repeats; i++) {
    try {
      console.log(`   🔸 تکرار وارپ ${i + 1}/${repeats}`);
      await sendTransaction(txObject, currentNonce);
      currentNonce++;
    } catch (error) {
      console.error(`   ❌ تکرار وارپ ${i + 1} شکست خورد. ادامه به تکرار بعدی...`);
    }
    await new Promise(resolve => setTimeout(resolve, 500)); // تاخیر کوتاه
  }
  return currentNonce;
}

/**
 * اجرای تراکنش آن‌استیک
 * @param {number} nonce - Nonce فعلی
 * @returns {Promise<number>} Nonce جدید
 */
async function executeUnstake(nonce) {
  console.log('\n--- 🔗 در حال اجرای تراکنش آن‌استیک ---');
  const config = ALL_TRANSACTIONS.find(t => t.type === 'UNSTAKE');
  const amountInSmallestUnit = toSmallestUnit(config.amount, TOKEN_DECIMALS.INJ);

  // ساخت فیلد data شامل Method ID و مقدار به عنوان پارامتر
  const paddedAmount = web3.utils.padLeft(web3.utils.toHex(amountInSmallestUnit), 64).substring(2);
  const data = config.methodId + paddedAmount;

  const txObject = {
    to: config.contract,
    value: '0x0', // مقدار اصلی از طریق data ارسال می‌شود
    gasLimit: config.gasLimit,
    data: data,
  };

  try {
    await sendTransaction(txObject, nonce);
    return nonce + 1;
  } catch (error) {
    console.error('❌ تراکنش آن‌استیک شکست خورد.');
    return nonce;
  }
}

/**
 * اجرای تراکنش سواپ USDT به wINJ و ذخیره خروجی
 * @param {number} nonce - Nonce فعلی
 * @param {string} runTimeKey - کلید زمان اجرا ("12:00" یا "19:00")
 * @returns {Promise<number>} Nonce جدید
 */
async function executeSwapUsdtToWinj(nonce, runTimeKey) {
  console.log('\n--- 💰 در حال اجرای تراکنش سواپ USDT به wINJ ---');
  const config = ALL_TRANSACTIONS.find(t => t.type === 'SWAP_USDT_TO_WINJ');
  const inputAmountWei = toSmallestUnit(config.inputAmount, TOKEN_DECIMALS.USDT);
  const minAmountOutWei = toSmallestUnit(config.minAmountOut, TOKEN_DECIMALS.SWAP_WINJ);

  const currentTimestamp = Math.floor(Date.now() / 1000);
  const deadline = BigInt(currentTimestamp + (60 * 10)); // 10 دقیقه از الان

  // بازسازی فیلد 'data' بر اساس نمونه ارسالی شما
  // 0x414bf389 (Method ID)
  // [path[0] - USDT] (32 bytes padded address)
  // [path[1] - SWAP_WINJ] (32 bytes padded address)
  // [amountIn] (32 bytes padded amount)
  // [to] (32 bytes padded address - recipient)
  // [deadline] (32 bytes padded timestamp)
  // [minAmountOut] (32 bytes padded amount)
  // [UNKNOWN_PARAM_1] (32 bytes, from sample: 0x00...036861bb4b0c4b) - مقدار ثابت از نمونه
  // [UNKNOWN_PARAM_2] (32 bytes, from sample: 0x00...0000) - مقدار ثابت از نمونه
  
  const data = web3.eth.abi.encodeFunctionCall({
    name: 'swapExactTokensForTokens', // نام متد واقعی (اگرچه فقط با methodId کار می‌کنیم)
    type: 'function',
    inputs: [
      {type: 'uint256', name: 'amountIn'},
      {type: 'uint256', name: 'amountOutMin'},
      {type: 'address[]', name: 'path'},
      {type: 'address', name: 'to'},
      {type: 'uint256', name: 'deadline'}
    ]
  }, [
    BigInt(inputAmountWei),
    BigInt(minAmountOutWei),
    [CONTRACT_ADDRESSES.USDT_TOKEN, CONTRACT_ADDRESSES.SWAP_WINJ_TOKEN],
    SENDER_ADDRESS,
    BigInt(deadline)
  ]).substring(2); // حذف '0x'

  // توجه: این تابع `encodeFunctionCall` برای ABI استاندارد Uniswap/Pancakeswap است.
  // نمونه Data شما (0x414bf389...) خیلی طولانی‌تر و پیچیده‌تر است و به نظر می‌رسد از فرمت استاندارد ABI پیروی نمی‌کند.
  // ممکن است تابع فراخوانی شده، پارامترهای بیشتری داشته باشد یا روتر DEX شما یک فرمت خاص برای ارسال دیتا داشته باشد.
  // برای دقت بیشتر، باید ABI دقیق قرارداد 0x822f872763B7Be16c9b9687D8b9D73f1b5017Df0 را داشته باشیم.
  // فعلاً، با توجه به `Method ID` و مقادیر مورد نیاز، تلاش می‌کنیم که دیتا را مشابه نمونه شما بسازیم.
  // این یک بازسازی تقریبی است و نیاز به تست دقیق دارد.

  // بازسازی Data بر اساس نمونه شما:
  // روش ساده‌تر: فقط Method ID را بگذاریم و بگوییم مقدار در value میاد.
  // اما شما value: 0x0 فرستادید و data یک رشته طولانی.
  // پس باید پارامترها در data Encode شوند.
  // با توجه به اینکه شما خود Data را به صورت Raw فرستادید،
  // دقیق‌ترین روش این است که آن را کپی کنیم و فقط مقدار inputAmount را تغییر دهیم.

  // --- بازسازی دقیق فیلد Data بر اساس نمونه شما (با جایگذاری مقدار inputAmount) ---
  // فرمت نمونه: MethodID + path[0] + path[1] + amountIn + to + deadline + minAmountOut + unknown1 + unknown2
  const fixedPart1 = '414bf389' + // Method ID
                     web3.utils.padLeft(CONTRACT_ADDRESSES.USDT_TOKEN.substring(2), 64) + // path[0] USDT
                     web3.utils.padLeft(CONTRACT_ADDRESSES.SWAP_WINJ_TOKEN.substring(2), 64); // path[1] SWAP_WINJ

  const fixedPart2 = web3.utils.padLeft(SENDER_ADDRESS.substring(2), 64) + // to address
                     web3.utils.padLeft(web3.utils.toHex(deadline), 64).substring(2) + // deadline
                     web3.utils.padLeft(web3.utils.toHex(minAmountOutWei), 64).substring(2); // minAmountOut

  // پارامترهای ناشناس انتهایی از نمونه شما
  const unknownParam1 = '00000000000000000000000000000000000000000000000000036861bb4b0c4b';
  const unknownParam2 = '0000000000000000000000000000000000000000000000000000000000000000';

  // مقدار ورودی دینامیک
  const amountInPadded = web3.utils.padLeft(web3.utils.toHex(inputAmountWei), 64).substring(2);

  const fullData = '0x' + fixedPart1 + amountInPadded + fixedPart2 + unknownParam1 + unknownParam2;

  const txObject = {
    to: config.contract,
    value: '0x0', // مقدار اصلی از طریق data ارسال می‌شود
    gasLimit: config.gasLimit,
    data: fullData,
  };

  let receipt;
  try {
    receipt = await sendTransaction(txObject, nonce);
  } catch (error) {
    console.error('❌ تراکنش سواپ USDT به wINJ شکست خورد.');
    return nonce;
  }

  // --- پس از موفقیت‌آمیز بودن تراکنش: دریافت مقدار wINJ دریافتی و ذخیره در فایل JSON ---
  let winjReceived = '0';
  if (receipt && receipt.logs) {
    const swapWinjTokenContract = new web3.eth.Contract(
      // ABI مینیمال برای Transfer event
      [{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"}],
      CONTRACT_ADDRESSES.SWAP_WINJ_TOKEN
    );

    // فیلتر کردن لاگ‌های Transfer از قرارداد wINJ به آدرس فرستنده شما
    const transferLogs = receipt.logs.filter(log =>
      log.address.toLowerCase() === CONTRACT_ADDRESSES.SWAP_WINJ_TOKEN.toLowerCase() &&
      log.topics.length === 3 && // Transfer event has 3 topics (signature + from + to)
      log.topics[2].toLowerCase() === web3.utils.padLeft(config.recipient.toLowerCase(), 64) // Check 'to' address in topics
    );

    if (transferLogs.length > 0) {
      // Decode the last Transfer event if multiple, or the most relevant one
      const decodedLog = web3.eth.abi.decodeLog(
        transferLogs[0].topics, // Topics excluding signature
        transferLogs[0].data,
        swapWinjTokenContract.options.jsonInterface.find(i => i.name === 'Transfer' && i.type === 'event').inputs
      );
      winjReceived = decodedLog.value.toString();
      console.log(`✨ دریافت شد: ${fromSmallestUnit(winjReceived, TOKEN_DECIMALS.SWAP_WINJ)} wINJ`);

      // ذخیره در فایل JSON
      const swapOutputs = await readSwapOutputs();
      swapOutputs[runTimeKey] = winjReceived;
      await writeSwapOutputs(swapOutputs);
    } else {
      console.warn('⚠️ اخطار: لاگ Transfer برای wINJ دریافتی پیدا نشد. مقدار 0 در فایل ذخیره می‌شود.');
    }
  }

  return nonce + 1;
}

/**
 * اجرای تراکنش سواپ wINJ به USDT با مقدار ورودی دینامیک
 * @param {number} nonce - Nonce فعلی
 * @param {string} runTimeKeyForInput - کلید زمان اجرای سواپ قبلی (مثلاً "12:00")
 * @returns {Promise<number>} Nonce جدید
 */
async function executeSwapWinjToUsdt(nonce, runTimeKeyForInput) {
  console.log('\n--- 💸 در حال اجرای تراکنش سواپ wINJ به USDT ---');
  const config = ALL_TRANSACTIONS.find(t => t.type === 'SWAP_WINJ_TO_USDT');

  // خواندن مقدار wINJ از فایل JSON
  const swapOutputs = await readSwapOutputs();
  const inputAmountWinj = swapOutputs[runTimeKeyForInput];

  if (!inputAmountWinj || BigInt(inputAmountWinj) === 0n) {
    console.warn(`⚠️ اخطار: هیچ wINJ برای سواپ در زمان ${runTimeKeyForInput} پیدا نشد یا مقدار آن 0 است. تراکنش انجام نمی‌شود.`);
    return nonce; // Nonce را افزایش نمی‌دهیم
  }

  console.log(`   🔸 سواپینگ ${fromSmallestUnit(inputAmountWinj, TOKEN_DECIMALS.SWAP_WINJ)} wINJ به USDT...`);

  const minAmountOutWei = toSmallestUnit(config.minAmountOut, TOKEN_DECIMALS.USDT);
  const currentTimestamp = Math.floor(Date.now() / 1000);
  const deadline = BigInt(currentTimestamp + (60 * 10)); // 10 دقیقه از الان

  // بازسازی فیلد 'data' بر اساس نمونه ارسالی شما (با جایگذاری مقدار inputAmountWinj)
  // فرمت نمونه: MethodID + path[0] + path[1] + amountIn + to + deadline + minAmountOut + unknown1 + unknown2
  const fixedPart1 = '414bf389' + // Method ID
                     web3.utils.padLeft(CONTRACT_ADDRESSES.SWAP_WINJ_TOKEN.substring(2), 64) + // path[0] SWAP_WINJ
                     web3.utils.padLeft(CONTRACT_ADDRESSES.USDT_TOKEN.substring(2), 64); // path[1] USDT

  const fixedPart2 = web3.utils.padLeft(SENDER_ADDRESS.substring(2), 64) + // to address
                     web3.utils.padLeft(web3.utils.toHex(deadline), 64).substring(2) + // deadline
                     web3.utils.padLeft(web3.utils.toHex(minAmountOutWei), 64).substring(2); // minAmountOut

  // پارامترهای ناشناس انتهایی از نمونه شما (همانند سواپ اول)
  const unknownParam1 = '00000000000000000000000000000000000000000000000000036861bb4b0c4b'; // از نمونه سواپ USDT به wINJ
  const unknownParam2 = '0000000000000000000000000000000000000000000000000000000000000000'; // از نمونه سواپ USDT به wINJ

  const amountInPadded = web3.utils.padLeft(web3.utils.toHex(inputAmountWinj), 64).substring(2);

  const fullData = '0x' + fixedPart1 + amountInPadded + fixedPart2 + unknownParam1 + unknownParam2;

  const txObject = {
    to: config.contract,
    value: '0x0', // مقدار اصلی از طریق data ارسال می‌شود
    gasLimit: config.gasLimit,
    data: fullData,
  };

  try {
    await sendTransaction(txObject, nonce);
    return nonce + 1;
  } catch (error) {
    console.error('❌ تراکنش سواپ wINJ به USDT شکست خورد.');
    return nonce;
  }
}

// --- 4. تابع اصلی اجرا (Main Execution Function) ---

async function main() {
  let currentNonce;
  try {
    currentNonce = await web3.eth.getTransactionCount(SENDER_ADDRESS, 'pending');
    console.log(`Current Nonce برای ${SENDER_ADDRESS}: ${currentNonce}`);
  } catch (error) {
    console.error('❌ خطا در دریافت Nonce اولیه:', error.message);
    process.exit(1);
  }

  const now = new Date();
  const currentHourUTC = now.getUTCHours();
  const currentMinuteUTC = now.getUTCMinutes();
  console.log(`⏰ زمان فعلی UTC: ${String(currentHourUTC).padStart(2, '0')}:${String(currentMinuteUTC).padStart(2, '0')}`);

  for (const txConfig of ALL_TRANSACTIONS) {
    let shouldRun = false;
    // بررسی زمان‌بندی: اگر schedule آرایه باشد (چندین زمان)، یا آبجکت باشد (یک زمان)
    const schedules = Array.isArray(txConfig.schedule) ? txConfig.schedule : [txConfig.schedule];

    for (const schedule of schedules) {
      if (currentHourUTC === schedule.hour && currentMinuteUTC >= schedule.minute && currentMinuteUTC < schedule.minute + 5) { // یک بازه 5 دقیقه‌ای برای شروع
        shouldRun = true;
        break;
      }
    }

    if (shouldRun) {
      console.log(`\n--- ⏳ زمان اجرای تراکنش "${txConfig.name}" فرا رسیده است! ---`);
      
      switch (txConfig.type) {
        case 'STAKE':
          currentNonce = await executeStake(currentNonce);
          break;
        case 'WARP':
          currentNonce = await executeWarp(currentNonce, txConfig.repeats);
          break;
        case 'UNSTAKE':
          currentNonce = await executeUnstake(currentNonce);
          break;
        case 'SWAP_USDT_TO_WINJ':
          // تعیین کلید برای ذخیره خروجی بر اساس زمان اجرا
          const runTimeKeyUsdtToWinj = `${String(currentHourUTC).padStart(2, '0')}:${String(currentMinuteUTC).padStart(2, '0')}`;
          currentNonce = await executeSwapUsdtToWinj(currentNonce, runTimeKeyUsdtToWinj);
          break;
        case 'SWAP_WINJ_TO_USDT':
            let inputKey;
            // تعیین کلید برای خواندن ورودی بر اساس زمان اجرا
            if (currentHourUTC === 20 && currentMinuteUTC >= 0) {
                inputKey = '12:00';
            } else if (currentHourUTC === 0 && currentMinuteUTC >= 0) { // 24:00 UTC is 00:00 next day
                inputKey = '19:00';
            } else {
                console.warn(`⚠️ اخطار: زمان اجرای نامشخص برای سواپ wINJ به USDT. (${currentHourUTC}:${currentMinuteUTC})`);
                break; // از اجرای این تراکنش صرف نظر می‌کنیم
            }
          currentNonce = await executeSwapWinjToUsdt(currentNonce, inputKey);
          break;
        default:
          console.warn(`⚠️ اخطار: نوع تراکنش ناشناخته: ${txConfig.type}`);
      }
    } else {
      console.log(`\n--- ⏭️ تراکنش "${txConfig.name}" در حال حاضر اجرا نمی‌شود. (${String(currentHourUTC).padStart(2, '0')}:${String(currentMinuteUTC).padStart(2, '0')} UTC) ---`);
    }
  }
  console.log('\n--- ✅ تمامی تراکنش‌های زمان‌بندی شده برای این اجرا بررسی شدند. ---');
}

// اجرای تابع اصلی
main().catch(error => {
  console.error('❌ خطا در اجرای اسکریپت اصلی:', error);
  process.exit(1);
});
