import os
import asyncio
from decimal import Decimal
from dotenv import load_dotenv
import bittensor as bt
import random

load_dotenv()

async def async_test_stake():
    print("Testing async Bittensor staking...")
    try:
        wallet = bt.wallet()
        if os.getenv('BT_MNEMONIC'):
            mnemonic = os.getenv('BT_MNEMONIC').strip()
            wallet.regenerate_coldkey(mnemonic=mnemonic, use_password=False, overwrite=True, suppress=True)
            print(f"Wallet loaded: {wallet.coldkey.ss58_address}")
        else:
            print("No mnemonic found")
            return False

        async with bt.AsyncSubtensor(os.getenv('BT_NETWORK', 'finney')) as subtensor:
            netuid = 11
            amount_tao = Decimal('0.001')
            balance = await subtensor.get_balance(wallet.coldkey.ss58_address)
            print(f"Balance: {balance}")
            
            # Get metagraph to fetch validator hotkeys dynamically
            print(f"Fetching metagraph for subnet {netuid}...")
            metagraph = await subtensor.metagraph(netuid=netuid)
            
            # Get validators (neurons with validator_permit = True)
            validators = [uid for uid, neuron in enumerate(metagraph.neurons) if neuron.validator_permit]
            
            if not validators:
                print("❌ No validators found in the subnet")
                return False
            
            # Select the top validator by stake
            top_validator_uid = max(validators, key=lambda uid: metagraph.neurons[uid].stake.tao)
            validator_hotkey_ss58 = metagraph.neurons[top_validator_uid].hotkey
            validator_stake = metagraph.neurons[top_validator_uid].stake.tao
            
            print(f"Selected top validator UID {top_validator_uid} with hotkey: {validator_hotkey_ss58}")
            print(f"Validator stake: {validator_stake} TAO")
            print(f"Attempting to stake {amount_tao} TAO to subnet {netuid}...")

            result = await subtensor.add_stake(
                wallet=wallet,
                hotkey_ss58=validator_hotkey_ss58,
                netuid=netuid,
                amount=bt.Balance.from_tao(amount_tao),
                wait_for_inclusion=True,
                wait_for_finalization=True
            )

            

            if result is True:
                print("✅ Stake successful!")
                return True
            else:
                print("❌ Stake failed")
                print(f"Result type: {type(result)}")
                print(f"Result content: {result}")
                if hasattr(result, '__dict__'):
                    print("Result attributes:")
                    for key, value in result.__dict__.items():
                        print(f"  {key}: {value}")
                return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(async_test_stake())
    exit(0 if success else 1)
