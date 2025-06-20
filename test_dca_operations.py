import asyncio
import os
from decimal import Decimal
from typing import Optional, Tuple
from dotenv import load_dotenv
import bittensor as bt

# Load environment variables
load_dotenv()

class DCAOperationTester:
    def __init__(self):
        # Initialize Bittensor components
        self.wallet = bt.wallet()
        
        # Load wallet from environment - try mnemonic first, then private key
        wallet_loaded = False
        
        if os.getenv('BT_MNEMONIC'):
            try:
                # Use mnemonic phrase (preferred method for bittensor)
                mnemonic = os.getenv('BT_MNEMONIC').strip()
                print(f"🔑 Loading wallet from mnemonic phrase...")
                self.wallet.regenerate_coldkey(mnemonic=mnemonic, use_password=False, overwrite=True, suppress=True)
                print("✅ Wallet loaded successfully from mnemonic")
                print(f"💰 Wallet address: {self.wallet.coldkey.ss58_address}")
                wallet_loaded = True
            except Exception as e:
                print(f"⚠️ Warning: Could not load wallet from mnemonic: {e}")
                
        if not wallet_loaded and os.getenv('BT_PRIVATE_KEY'):
            try:
                # In bittensor 7.0.0, use regenerate_coldkey with seed parameter
                private_key = os.getenv('BT_PRIVATE_KEY')
                # Remove '0x' prefix if present
                if private_key.startswith('0x'):
                    private_key = private_key[2:]
                
                print(f"🔑 Loading wallet from private key...")
                self.wallet.regenerate_coldkey(seed=private_key, use_password=False, overwrite=True)
                print("✅ Wallet loaded successfully from private key")
                print(f"💰 Wallet address: {self.wallet.coldkey.ss58_address}")
                wallet_loaded = True
            except Exception as e:
                print(f"⚠️ Warning: Could not load private key from environment: {e}")
                
        if not wallet_loaded:
            print("⚠️ Warning: Using default wallet (no mnemonic or private key loaded)")
            print(f"💰 Default wallet address: {self.wallet.coldkey.ss58_address}")
        
        # Initialize subtensor for bittensor 7.0.0
        network = os.getenv('BT_NETWORK', 'finney')
        self.subtensor = bt.subtensor(network=network)

    async def execute_buy_operation(self, subnet_id: int, amount_tao: Decimal) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Execute a buy operation by staking TAO to the top validator in the subnet.
        
        Returns:
            tuple: (success: bool, error_message: str, transaction_hash: str)
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                print(f"🔄 Executing buy operation: {amount_tao} TAO to subnet {subnet_id} (attempt {attempt + 1}/{max_retries})")
                
                # Use AsyncSubtensor for async operations
                async with bt.AsyncSubtensor(os.getenv('BT_NETWORK', 'finney')) as subtensor:
                    # Get metagraph to fetch validator hotkeys dynamically
                    print(f"📊 Fetching metagraph for subnet {subnet_id}...")
                    metagraph = await subtensor.metagraph(netuid=subnet_id)
                    
                    # Get validators (neurons with validator_permit = True)
                    validators = [uid for uid, neuron in enumerate(metagraph.neurons) if neuron.validator_permit]
                    
                    if not validators:
                        return False, f"No validators found in subnet {subnet_id}", None
                    
                    # Select the top validator by stake
                    top_validator_uid = max(validators, key=lambda uid: metagraph.neurons[uid].stake.tao)
                    validator_hotkey_ss58 = metagraph.neurons[top_validator_uid].hotkey
                    validator_stake = metagraph.neurons[top_validator_uid].stake.tao
                    
                    print(f"🎯 Selected top validator UID {top_validator_uid} with hotkey: {validator_hotkey_ss58}")
                    print(f"📈 Validator stake: {validator_stake} TAO")
                    print(f"💰 Staking {amount_tao} TAO to subnet {subnet_id}...")
                    
                    # Execute the stake transaction
                    result = await subtensor.add_stake(
                        wallet=self.wallet,
                        hotkey_ss58=validator_hotkey_ss58,
                        netuid=subnet_id,
                        amount=bt.Balance.from_tao(amount_tao),
                        wait_for_inclusion=True,
                        wait_for_finalization=True
                    )
                    
                    if result is True:
                        print("✅ Stake successful!")
                        return True, None, "success"
                    else:
                        print(f"❌ Stake failed - Result: {result}")
                        return False, f"Stake operation failed: {result}", None
                    
            except Exception as e:
                error_msg = f"Staking error: {str(e)}"
                print(f"❌ Attempt {attempt + 1} failed: {error_msg}")
                
                # Retry with delay if not last attempt
                if attempt < max_retries - 1:
                    print(f"⏳ Retrying in 5 seconds...")
                    await asyncio.sleep(5)
                else:
                    print(f"💥 All attempts failed: {error_msg}")
                    return False, error_msg, None
        
        return False, "All retry attempts failed", None

    async def execute_sell_operation(self, subnet_id: int, amount_alpha: Decimal) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Execute a sell operation by unstaking alpha tokens from the top validator in the subnet.
        
        Returns:
            tuple: (success: bool, error_message: str, transaction_hash: str)
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                print(f"🔄 Executing sell operation: {amount_alpha} Alpha from subnet {subnet_id} (attempt {attempt + 1}/{max_retries})")
                
                # Use AsyncSubtensor for async operations
                async with bt.AsyncSubtensor(os.getenv('BT_NETWORK', 'finney')) as subtensor:
                    # Get metagraph to fetch validator hotkeys dynamically
                    print(f"📊 Fetching metagraph for subnet {subnet_id}...")
                    metagraph = await subtensor.metagraph(netuid=subnet_id)
                    
                    # Get validators with stake from our wallet
                    validators_with_stake = []
                    our_coldkey = self.wallet.coldkey.ss58_address
                    
                    for uid, neuron in enumerate(metagraph.neurons):
                        if neuron.validator_permit:
                            # Check if we have stake with this validator
                            stake_amount = await subtensor.get_stake(
                                coldkey_ss58=our_coldkey,
                                hotkey_ss58=neuron.hotkey,
                                netuid=subnet_id
                            )
                            if stake_amount > 0:
                                validators_with_stake.append((uid, neuron.hotkey, stake_amount))
                    
                    if not validators_with_stake:
                        return False, f"No staked validators found in subnet {subnet_id}", None
                    
                    # Select the validator with the most stake from our wallet
                    top_validator = max(validators_with_stake, key=lambda x: x[2])
                    validator_uid, validator_hotkey_ss58, our_stake = top_validator
                    
                    print(f"🎯 Selected validator UID {validator_uid} with hotkey: {validator_hotkey_ss58}")
                    print(f"💎 Our stake with this validator: {our_stake} TAO")
                    
                    # Check if we have enough stake to sell (our_stake is in TAO, amount_alpha is alpha amount we want to unstake)
                    if our_stake < amount_alpha:
                        print(f"❌ Insufficient stake: have {our_stake} TAO, need {amount_alpha} Alpha")
                        return False, f"Insufficient stake: have {our_stake} TAO, need {amount_alpha} Alpha", None
                    
                    print(f"💰 Unstaking {amount_alpha} Alpha from subnet {subnet_id}...")
                    
                    # Execute the unstake transaction
                    result = await subtensor.unstake(
                        wallet=self.wallet,
                        hotkey_ss58=validator_hotkey_ss58,
                        netuid=subnet_id,
                        amount=bt.Balance.from_rao(float(amount_alpha)),
                        wait_for_inclusion=True,
                        wait_for_finalization=True
                    )
                    
                    if result is True:
                        print("✅ Unstake successful!")
                        return True, None, "success"
                    else:
                        print(f"❌ Unstake failed - Result: {result}")
                        return False, f"Unstake operation failed: {result}", None
                    
            except Exception as e:
                error_msg = f"Unstaking error: {str(e)}"
                print(f"❌ Attempt {attempt + 1} failed: {error_msg}")
                
                # Retry with delay if not last attempt
                if attempt < max_retries - 1:
                    print(f"⏳ Retrying in 5 seconds...")
                    await asyncio.sleep(5)
                else:
                    print(f"💥 All attempts failed: {error_msg}")
                    return False, error_msg, None
        
        return False, "All retry attempts failed", None

    async def check_wallet_balance(self):
        """Check and display wallet balance."""
        try:
            # Get wallet balance using coldkey
            balance = self.subtensor.get_balance(self.wallet.coldkey.ss58_address)
            print(f"💰 Wallet Balance: {balance.tao:.6f} TAO")
            return balance.tao
        except Exception as e:
            print(f"❌ Error fetching balance: {str(e)}")
            return 0.0

    async def get_stake_info(self, subnet_id: int):
        """Get stake information for the subnet."""
        try:
            async with bt.AsyncSubtensor(os.getenv('BT_NETWORK', 'finney')) as subtensor:
                metagraph = await subtensor.metagraph(netuid=subnet_id)
                our_coldkey = self.wallet.coldkey.ss58_address
                
                total_stake = 0.0
                stake_count = 0
                
                for uid, neuron in enumerate(metagraph.neurons):
                    if neuron.validator_permit:
                        stake_amount = await subtensor.get_stake(
                            coldkey_ss58=our_coldkey,
                            hotkey_ss58=neuron.hotkey,
                            netuid=subnet_id
                        )
                        if stake_amount > 0:
                            total_stake += float(stake_amount)
                            stake_count += 1
                            print(f"📍 Validator UID {uid}: {stake_amount:.6f} TAO staked")
                
                print(f"📊 Total stake in subnet {subnet_id}: {total_stake:.6f} TAO across {stake_count} validators")
                return total_stake
                
        except Exception as e:
            print(f"❌ Error getting stake info: {str(e)}")
            return 0.0

    async def run_test(self):
        """Run the complete test sequence."""
        print("🚀 Starting DCA Operations Test")
        print("=" * 50)
        
        # Test parameters
        subnet_id = 98
        buy_amount_tao = Decimal('0.001')
        sell_amount_alpha = Decimal('0.2')
        
        # Check initial wallet balance
        print("\n📋 Initial State:")
        initial_balance = await self.check_wallet_balance()
        initial_stake = await self.get_stake_info(subnet_id)
        
       
        
        # Test 2: Sell Operation (Unstake Alpha)
        print("\n" + "=" * 50)
        print("💰 TEST 2: SELL OPERATION (Unstake Alpha)")
        print("=" * 50)
        
        sell_success, sell_error, sell_tx = await self.execute_sell_operation(subnet_id, sell_amount_alpha)
        
        if sell_success:
            print("✅ Sell operation completed successfully!")
            
            # Check final balance
            print("\n📋 After Sell Operation:")
            final_balance = await self.check_wallet_balance()
            final_stake = await self.get_stake_info(subnet_id)
            
            print(f"   Balance change: {post_buy_balance:.6f} → {final_balance:.6f} TAO ({final_balance - post_buy_balance:.6f})")
            print(f"   Stake change: {post_buy_stake:.6f} → {final_stake:.6f} TAO ({final_stake - post_buy_stake:.6f})")
            
            # Summary
            print("\n" + "=" * 50)
            print("📊 TEST SUMMARY")
            print("=" * 50)
            print(f"✅ Buy Operation: {'SUCCESS' if buy_success else 'FAILED'}")
            print(f"✅ Sell Operation: {'SUCCESS' if sell_success else 'FAILED'}")
            print(f"\n💰 Overall Balance Change: {initial_balance:.6f} → {final_balance:.6f} TAO ({final_balance - initial_balance:.6f})")
            print(f"📈 Overall Stake Change: {initial_stake:.6f} → {final_stake:.6f} TAO ({final_stake - initial_stake:.6f})")
            
            return True
            
        else:
            print(f"❌ Sell operation failed: {sell_error}")
            return False

async def main():
    """Main function to run the test."""
    try:
        # Verify required environment variables
        required_vars = ['BT_NETWORK']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if not os.getenv('BT_MNEMONIC') and not os.getenv('BT_PRIVATE_KEY'):
            missing_vars.append('BT_MNEMONIC or BT_PRIVATE_KEY')
        
        if missing_vars:
            print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
            print("Please set these in your .env file or environment.")
            return
        
        # Create and run tester
        tester = DCAOperationTester()
        success = await tester.run_test()
        
        if success:
            print("\n🎉 All tests completed successfully!")
        else:
            print("\n💥 Tests failed!")
            
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")

if __name__ == "__main__":
    print("🧪 Bittensor DCA Operations Test Script")
    print("This script will test both buy and sell operations on subnet 98")
    print("Make sure you have sufficient TAO balance for testing")
    print()
    
    asyncio.run(main()) 