"""
genesis_core.py - Phase 1: The Math Core (Universe Physics)

The deterministic PRNG wrapper and cascade function implementation.
This forms the mathematical foundation of the Genesis Protocol.
"""

import numpy as np
import hashlib
import struct
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class CascadeNode:
    """Represents a node in the seed cascade tree."""
    seed: int
    index: int
    depth: int
    data: Optional[bytes] = None
    children: List['CascadeNode'] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []


class Xorshift64Star:
    """
    High-quality 64-bit Xorshift PRNG with multiplicative scramble.
    Period: 2^64 - 1
    """
    
    MASK = (1 << 64) - 1  # 64-bit mask
    
    def __init__(self, seed: int):
        """Initialize with a 64-bit seed."""
        self.state = seed & self.MASK
        if self.state == 0:
            self.state = 1  # Prevent zero state
    
    def next(self) -> int:
        """Generate next random number."""
        x = self.state
        x ^= (x >> 12) & self.MASK
        x ^= (x << 25) & self.MASK
        x ^= (x >> 27) & self.MASK
        self.state = x
        # Multiply by large prime for better distribution
        return ((x * 0x2545F4914F6CDD1D) & self.MASK)
    
    def next_bytes(self, n_bytes: int) -> bytes:
        """Generate n_bytes of random data."""
        result = bytearray()
        while len(result) < n_bytes:
            val = self.next()
            result.extend(struct.pack('<Q', val))
        return bytes(result[:n_bytes])
    
    def clone(self) -> 'Xorshift64Star':
        """Create a copy with same state."""
        new_gen = Xorshift64Star(0)
        new_gen.state = self.state
        return new_gen
    
    @staticmethod
    def from_seed_index(master_seed: int, index: int) -> 'Xorshift64Star':
        """
        Generate a deterministic subseed generator from master seed and index.
        This is the core of the cascade function.
        """
        # Mix master seed with index using hash for better distribution
        combined = hashlib.sha256(
            struct.pack('<QQ', master_seed, index)
        ).digest()
        subseed = struct.unpack('<Q', combined[:8])[0]
        return Xorshift64Star(subseed)


class CascadeGenerator:
    """
    Implements the seed cascade system.
    Master Seed → Subseeds → Data Chunks
    """
    
    CHUNK_SIZE = 4096  # 4KB chunks
    MAX_DEPTH = 8      # Maximum cascade depth
    
    def __init__(self, master_seed: int):
        self.master_seed = master_seed
        self.cache = {}  # Cache generated subseeds
    
    def generate_subseed(self, index: int, depth: int = 0) -> int:
        """
        Cascade Function: Generate a deterministic subseed from master seed.
        
        Args:
            index: Position in the cascade tree
            depth: Depth level (0 = direct children of master)
            
        Returns:
            64-bit subseed value
        """
        cache_key = (index, depth)
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        if depth == 0:
            # Direct child of master seed
            gen = Xorshift64Star.from_seed_index(self.master_seed, index)
            subseed = gen.next()
        else:
            # Recursive: parent subseed generates this one
            parent_idx = index // 256  # 256 children per node
            parent_depth = depth - 1
            parent_seed = self.generate_subseed(parent_idx, parent_depth)
            local_idx = index % 256
            gen = Xorshift64Star.from_seed_index(parent_seed, local_idx)
            subseed = gen.next()
        
        self.cache[cache_key] = subseed
        return subseed
    
    def generate_chunk(self, chunk_index: int, size: int = CHUNK_SIZE) -> bytes:
        """
        Generate a deterministic data chunk from the cascade.
        
        Args:
            chunk_index: Which chunk to generate
            size: Size of chunk in bytes
            
        Returns:
            Deterministic byte sequence
        """
        subseed = self.generate_subseed(chunk_index)
        gen = Xorshift64Star(subseed)
        return gen.next_bytes(size)
    
    def generate_file(self, total_size: int) -> bytes:
        """
        Generate an entire file deterministically from master seed.
        
        Args:
            total_size: Total file size in bytes
            
        Returns:
            Complete file content
        """
        result = bytearray()
        n_chunks = (total_size + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE
        
        for i in range(n_chunks):
            remaining = total_size - len(result)
            chunk_size = min(self.CHUNK_SIZE, remaining)
            chunk = self.generate_chunk(i, chunk_size)
            result.extend(chunk)
        
        return bytes(result)
    
    def build_cascade_tree(self, max_depth: int = 2, children_per_node: int = 4) -> CascadeNode:
        """
        Build a visual representation of the cascade tree.
        
        Args:
            max_depth: How deep to build the tree
            children_per_node: Branching factor
            
        Returns:
            Root CascadeNode with children
        """
        root = CascadeNode(seed=self.master_seed, index=-1, depth=0)
        self._build_tree_recursive(root, max_depth, children_per_node)
        return root
    
    def _build_tree_recursive(self, node: CascadeNode, max_depth: int, branching: int):
        """Recursively build cascade tree."""
        if node.depth >= max_depth:
            return
        
        for i in range(branching):
            child_index = (node.index + 1) * branching + i if node.index >= 0 else i
            subseed = self.generate_subseed(child_index, node.depth)
            child = CascadeNode(seed=subseed, index=child_index, depth=node.depth + 1)
            node.children.append(child)
            self._build_tree_recursive(child, max_depth, branching)


class SeedMetadata:
    """
    Metadata structure for encoding/decoding files.
    """
    
    MAGIC = b'GENESIS01'
    VERSION = 1
    
    @staticmethod
    def pack(master_seed: int, file_size: int, chunk_count: int, 
             is_procedural: bool, entropy_score: float) -> bytes:
        """Pack metadata into binary format."""
        flags = (1 if is_procedural else 0)
        entropy_int = int(entropy_score * 1000)  # 3 decimal places
        
        return struct.pack(
            '<8sBQQQBI',
            SeedMetadata.MAGIC,
            SeedMetadata.VERSION,
            master_seed,
            file_size,
            chunk_count,
            flags,
            entropy_int
        )
    
    @staticmethod
    def unpack(data: bytes) -> dict:
        """Unpack metadata from binary format."""
        if len(data) < 37:
            raise ValueError("Invalid metadata size")
        
        magic, version, master_seed, file_size, chunk_count, flags, entropy_int = struct.unpack(
            '<8sBQQQBI', data[:37]
        )
        
        if magic != SeedMetadata.MAGIC:
            raise ValueError("Invalid magic bytes")
        
        return {
            'version': version,
            'master_seed': master_seed,
            'file_size': file_size,
            'chunk_count': chunk_count,
            'is_procedural': bool(flags),
            'entropy_score': entropy_int / 1000.0
        }


def calculate_entropy(data: bytes) -> float:
    """
    Calculate Shannon entropy of data (0.0 to 8.0 for bytes).
    Higher entropy = more random = harder to compress to seed.
    """
    if len(data) == 0:
        return 0.0
    
    # Count byte frequencies
    freq = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    probs = freq / len(data)
    
    # Calculate entropy
    probs = probs[probs > 0]  # Remove zeros to avoid log(0)
    entropy = -np.sum(probs * np.log2(probs))
    
    return float(entropy)


if __name__ == "__main__":
    # Test the core functionality
    print("=" * 60)
    print("GENESIS CORE - Phase 1 Test")
    print("=" * 60)
    
    # Test PRNG
    master_seed = 0xDEADBEEF12345678
    gen = Xorshift64Star(master_seed)
    print(f"\nMaster Seed: 0x{master_seed:016X}")
    print(f"First 5 values: {[hex(gen.next()) for _ in range(5)]}")
    
    # Test cascade
    cascade = CascadeGenerator(master_seed)
    print(f"\nCascade Subseeds:")
    for i in range(5):
        subseed = cascade.generate_subseed(i)
        print(f"  Index {i}: 0x{subseed:016X}")
    
    # Test file generation
    test_size = 10240  # 10KB
    file_data = cascade.generate_file(test_size)
    print(f"\nGenerated {len(file_data)} bytes")
    print(f"First 32 bytes: {file_data[:32].hex()}")
    
    # Verify determinism
    cascade2 = CascadeGenerator(master_seed)
    file_data2 = cascade2.generate_file(test_size)
    assert file_data == file_data2, "Determinism check failed!"
    print("✓ Determinism verified")
    
    # Test entropy calculation
    random_data = np.random.randint(0, 256, 10000, dtype=np.uint8).tobytes()
    entropy = calculate_entropy(random_data)
    print(f"\nRandom data entropy: {entropy:.3f} bits/byte (max: 8.0)")
    
    # Low entropy data
    low_entropy = bytes([i % 16 for i in range(10000)])
    entropy_low = calculate_entropy(low_entropy)
    print(f"Low entropy data: {entropy_low:.3f} bits/byte")
    
    print("\n" + "=" * 60)
    print("Phase 1 Complete - Math Core Ready")
    print("=" * 60)
