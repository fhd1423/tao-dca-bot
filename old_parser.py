import bittensor as bt
import time
import json
import re

# Connect to the network
subtensor = bt.subtensor(network="finney")

def get_wallet_balance(address: str, hotkey: str = None, netuid: int = None) -> tuple:
    """Get both liquid and staked TAO balances of a wallet address."""
    try:
        # Get the liquid balance in Rao (raw units)
        balance_rao = subtensor.get_balance(address)
        # Convert to TAO (1 TAO = 1,000,000,000 Rao)
        balance_tao = float(balance_rao) 
        
        # Get staked amount if hotkey and netuid are provided
        staked_tao = 0.0
        if hotkey and netuid is not None:
            try:
                stake_info = subtensor.get_stake(coldkey_ss58=address, hotkey_ss58=hotkey, netuid=netuid)
                if stake_info:
                    staked_tao = float(stake_info)
            except Exception as e:
                print(f"Error getting stake info for {address} -> {hotkey} on subnet {netuid}: {e}")
        
        return balance_tao, staked_tao
    except Exception as e:
        print(f"Error getting balance for {address}: {e}")
        return 0.0, 0.0

# Helper function to parse and categorize transactions
def parse_transaction(tx_str: str) -> dict:
    """Parse a transaction string and return relevant information."""
    try:
        # Extract the call function and module
        call_function_match = re.search(r"'call_function': '([^']+)'", tx_str)
        call_module_match = re.search(r"'call_module': '([^']+)'", tx_str)
        
        if not call_function_match or not call_module_match:
            return None
            
        call_function = call_function_match.group(1)
        call_module = call_module_match.group(1)
        
        # Only process SubtensorModule transactions
        if call_module != 'SubtensorModule':
            return None
            
        # Extract the sender address
        sender_match = re.search(r"'address': '([^']+)'", tx_str)
        sender = sender_match.group(1) if sender_match else None
        
        # Extract call_args for easier parsing
        call_args_match = re.search(r"'call_args': (\[.*?\])", tx_str, re.DOTALL)
        if not call_args_match:
            return None
            
        call_args_str = call_args_match.group(1)
        
        # Initialize variables
        hotkey = None
        netuid = None
        amount = 0.0
        
        # Parse based on transaction type
        if call_function == 'add_stake':
            # Extract hotkey
            hotkey_match = re.search(r"'name': 'hotkey'[^}]*'value': '([^']+)'", call_args_str)
            hotkey = hotkey_match.group(1) if hotkey_match else None
            
            # Extract netuid
            netuid_match = re.search(r"'name': 'netuid'[^}]*'value': (\d+)", call_args_str)
            netuid = int(netuid_match.group(1)) if netuid_match else None
            
            # Extract amount
            amount_match = re.search(r"'name': 'amount_staked'[^}]*'value': (\d+)", call_args_str)
            if amount_match:
                amount = float(amount_match.group(1)) / 1_000_000_000  # Convert Rao to TAO
                
        elif call_function == 'remove_stake':
            # Extract hotkey
            hotkey_match = re.search(r"'name': 'hotkey'[^}]*'value': '([^']+)'", call_args_str)
            hotkey = hotkey_match.group(1) if hotkey_match else None
            
            # Extract netuid
            netuid_match = re.search(r"'name': 'netuid'[^}]*'value': (\d+)", call_args_str)
            netuid = int(netuid_match.group(1)) if netuid_match else None
            
            # Extract amount
            amount_match = re.search(r"'name': 'amount_unstaked'[^}]*'value': (\d+)", call_args_str)
            if amount_match:
                amount = float(amount_match.group(1)) / 1_000_000_000  # Convert Rao to TAO
                
        elif call_function == 'move_stake':
            # Extract origin hotkey
            origin_hotkey_match = re.search(r"'name': 'origin_hotkey'[^}]*'value': '([^']+)'", call_args_str)
            hotkey = origin_hotkey_match.group(1) if origin_hotkey_match else None
            
            # Extract origin netuid
            origin_netuid_match = re.search(r"'name': 'origin_netuid'[^}]*'value': (\d+)", call_args_str)
            netuid = int(origin_netuid_match.group(1)) if origin_netuid_match else None
            
            # Extract amount
            amount_match = re.search(r"'name': 'alpha_amount'[^}]*'value': (\d+)", call_args_str)
            if amount_match:
                amount = float(amount_match.group(1)) / 1_000_000_000  # Convert Rao to TAO
                
        elif call_function in ['add_stake_limit', 'remove_stake_limit']:
            # Extract hotkey
            hotkey_match = re.search(r"'name': 'hotkey'[^}]*'value': '([^']+)'", call_args_str)
            hotkey = hotkey_match.group(1) if hotkey_match else None
            
            # Extract netuid
            netuid_match = re.search(r"'name': 'netuid'[^}]*'value': (\d+)", call_args_str)
            netuid = int(netuid_match.group(1)) if netuid_match else None
            
            # Extract amount
            amount_match = re.search(r"'name': '(amount_staked|amount_unstaked)'[^}]*'value': (\d+)", call_args_str)
            if amount_match:
                amount = float(amount_match.group(2)) / 1_000_000_000  # Convert Rao to TAO
        
        # Get balances including staked amount
        liquid_balance, staked_balance = get_wallet_balance(sender, hotkey, netuid)
        
        # Create the result dictionary
        result = {
            "type": call_function,
            "sender": sender,
            "receiver": None,  # No receiver in staking operations
            "hotkey": hotkey,
            "netuid": netuid,
            "amount": amount,
            "liquid_balance": liquid_balance,
            "staked_balance": staked_balance
        }
        
        # For move_stake operations, include the call_args for destination info
        if call_function == 'move_stake':
            result['call_args'] = call_args_str
            
        return result
    except Exception as e:
        print(f"Error parsing transaction: {e}")
        return None

def format_transaction_message(tx_info: dict) -> str:
    """Format transaction information into a message string that matches the expected patterns."""
    if not tx_info:
        return None
        
    tx_type = tx_info['type']
    sender = tx_info['sender']
    amount = tx_info['amount']
    amount_rao = int(amount * 1_000_000_000)  # Convert back to Rao for display
    hotkey = tx_info['hotkey']
    netuid = tx_info['netuid']
    liquid_balance = tx_info['liquid_balance']
    staked_balance = tx_info['staked_balance']
    
    if tx_type == 'add_stake':
        return f"STAKE: {sender} added {amount:.9f} TAO ({amount_rao} Rao) to validator {hotkey} on Subnet #{netuid} [TAO: {liquid_balance:.9f}, ALPHA: {staked_balance:.9f}]"
    elif tx_type == 'remove_stake':
        return f"UNSTAKE: {sender} removed {amount:.9f} alpha ({amount_rao} raw) from validator {hotkey} on Subnet #{netuid} [TAO: {liquid_balance:.9f}, ALPHA: {staked_balance:.9f}]"
    elif tx_type == 'move_stake':
        # For move_stake, we need to extract destination info from call_args
        dest_hotkey_match = re.search(r"'name': 'destination_hotkey'[^}]*'value': '([^']+)'", str(tx_info.get('call_args', '')))
        dest_netuid_match = re.search(r"'name': 'destination_netuid'[^}]*'value': (\d+)", str(tx_info.get('call_args', '')))
        
        dest_hotkey = dest_hotkey_match.group(1) if dest_hotkey_match else "unknown"
        dest_netuid = dest_netuid_match.group(1) if dest_netuid_match else "unknown"
        
        return f"MOVE: {sender} moved {amount:.9f} TAO ({amount_rao} Rao) from validator {hotkey} on Subnet #{netuid} to validator {dest_hotkey} on Subnet #{dest_netuid} [TAO: {liquid_balance:.9f}, ALPHA: {staked_balance:.9f}]"
    elif tx_type == 'add_stake_limit':
        return f"STAKE_LIMIT: {sender} added stake limit of {amount:.9f} TAO ({amount_rao} Rao) for validator {hotkey} on Subnet #{netuid} [TAO: {liquid_balance:.9f}, ALPHA: {staked_balance:.9f}]"
    elif tx_type == 'remove_stake_limit':
        return f"STAKE_LIMIT: {sender} removed stake limit of {amount:.9f} alpha ({amount_rao} raw) for validator {hotkey} on Subnet #{netuid} [TAO: {liquid_balance:.9f}, ALPHA: {staked_balance:.9f}]"
    
    return None

# Define function to process blocks
def process_blocks():
    print("Starting to monitor the Bittensor blockchain for staking operations...")
    
    # Get current block
    current_block = subtensor.get_current_block()
    print(f"Current block: {current_block}")
    
    # Monitor for new blocks
    while True:
        try:
            # Get latest block
            new_block = subtensor.get_current_block()
            
            # If we have a new block
            if new_block > current_block:
                print(f"New block detected: {new_block}")
                
                # Get block hash
                block_hash = subtensor.get_block_hash(new_block)
                
                # Get block data
                block = subtensor.substrate.get_block(block_hash)

                with open('FULL_BLOCK.txt', 'a') as f:
                    f.write(f"{block}\n")
                
                # Process extrinsics in the block
                if 'extrinsics' in block:
                    for idx, extrinsic in enumerate(block['extrinsics']):
                        # Try to extract extrinsic info
                        try:
                            with open('tx_blobs.txt', 'a') as f:
                                f.write(f"{extrinsic}")
                            # Convert extrinsic to string for easier parsing
                            extrinsic_str = str(extrinsic)
                            
                            # Parse the transaction
                            transaction_info = parse_transaction(extrinsic_str)
                            if transaction_info:
                                print(transaction_info)
                                
                                # Format the transaction message
                                formatted_message = format_transaction_message(transaction_info)
                                if formatted_message:
                                    # Log staking operations
                                    with open('staking_ops.txt', 'a') as f:
                                        f.write(f"Block {new_block}, Extrinsic {idx}: {formatted_message}\n")
                                
                        except Exception as e:
                            print(f"Error processing extrinsic: {e}")
                            with open('error_log.txt', 'a') as f:
                                f.write(f"Block {new_block}, Extrinsic {idx}: {str(e)}\n")
                
                # Update current block
                current_block = new_block
            
            # Sleep to avoid high CPU usage
            time.sleep(1)
            
        except Exception as e:
            print(f"Error processing block: {e}")
            with open('error_log.txt', 'a') as f:
                f.write(f"Error processing block {new_block}: {str(e)}\n")
            time.sleep(5)

# Start monitoring
if __name__ == "__main__":
    process_blocks()
