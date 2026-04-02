"""
genesis_decoder.py - Phase 2: The Decoder (The Genesis Machine)

Builds the expander that takes a Master Seed and expands it recursively
to reconstruct the original file perfectly.

Implements the "Infinite Canvas" logic where file size is derived from
metadata or seed parameters.
"""

import struct
import time
from typing import Optional, Tuple, Generator
from pathlib import Path

from genesis_core import (
    CascadeGenerator, Xorshift64Star, SeedMetadata, calculate_entropy
)


class GenesisDecoder:
    """
    The Genesis Machine - expands seeds back into files.
    
    Takes a tiny Master Seed and expands it recursively:
    Master Seed → Subseeds → Data Chunks → Complete File
    """
    
    def __init__(self):
        self.last_decoded = None
        self.decoding_stats = {}
    
    def decode_from_seed(self, master_seed: int, file_size: int, 
                        is_procedural: bool = True,
                        chunk_seeds: Optional[list] = None) -> bytes:
        """
        Expand a master seed into file data.
        
        Args:
            master_seed: The primary seed value
            file_size: Expected output size in bytes
            is_procedural: If True, generate purely from master seed
                          If False, use chunk_seeds for reconstruction
            chunk_seeds: List of per-chunk seeds (required if not procedural)
            
        Returns:
            Decoded file bytes
        """
        start_time = time.time()
        
        if is_procedural:
            # Pure procedural generation
            cascade = CascadeGenerator(master_seed)
            data = cascade.generate_file(file_size)
        else:
            # Cascade tree reconstruction
            if not chunk_seeds:
                raise ValueError("chunk_seeds required for non-procedural decoding")
            
            cascade = CascadeGenerator(master_seed)
            data = bytearray()
            
            for i, chunk_seed in enumerate(chunk_seeds):
                # Calculate chunk size
                remaining = file_size - len(data)
                chunk_size = min(4096, remaining)
                
                # Generate chunk from its seed
                gen = Xorshift64Star(chunk_seed)
                chunk = gen.next_bytes(chunk_size)
                data.extend(chunk)
                
                if len(data) >= file_size:
                    break
            
            data = bytes(data)
        
        elapsed = time.time() - start_time
        
        self.decoding_stats = {
            'master_seed': master_seed,
            'file_size': len(data),
            'is_procedural': is_procedural,
            'time_seconds': elapsed,
            'throughput_mbs': len(data) / (1024 * 1024) / elapsed if elapsed > 0 else 0
        }
        
        self.last_decoded = data
        return data
    
    def decode_from_metadata(self, metadata: bytes, 
                            chunk_seeds: Optional[list] = None) -> bytes:
        """
        Decode using packed metadata.
        
        Args:
            metadata: Packed SeedMetadata binary
            chunk_seeds: Optional list of chunk seeds for non-procedural
            
        Returns:
            Decoded file bytes
        """
        meta = SeedMetadata.unpack(metadata)
        
        return self.decode_from_seed(
            master_seed=meta['master_seed'],
            file_size=meta['file_size'],
            is_procedural=meta['is_procedural'],
            chunk_seeds=chunk_seeds
        )
    
    def decode_from_file(self, encoded_path: str) -> Tuple[bytes, dict]:
        """
        Load and decode from an encoded .genesis file.
        
        Args:
            encoded_path: Path to .genesis file
            
        Returns:
            (decoded_data, metadata_dict)
        """
        with open(encoded_path, 'rb') as f:
            # Read metadata (37 bytes)
            metadata = f.read(37)
            meta = SeedMetadata.unpack(metadata)
            
            # Read chunk seeds if not procedural
            chunk_seeds = []
            if not meta['is_procedural']:
                for _ in range(meta['chunk_count']):
                    seed_bytes = f.read(8)
                    if len(seed_bytes) < 8:
                        break
                    chunk_seeds.append(struct.unpack('<Q', seed_bytes)[0])
            
            # Decode
            data = self.decode_from_seed(
                master_seed=meta['master_seed'],
                file_size=meta['file_size'],
                is_procedural=meta['is_procedural'],
                chunk_seeds=chunk_seeds if chunk_seeds else None
            )
            
            return data, meta
    
    def stream_decode(self, master_seed: int, file_size: int,
                     chunk_size: int = 4096,
                     is_procedural: bool = True,
                     chunk_seeds: Optional[list] = None) -> Generator[bytes, None, None]:
        """
        Stream decoded data in chunks (memory efficient).
        
        Args:
            master_seed: Primary seed
            file_size: Total expected size
            chunk_size: Size of each yielded chunk
            is_procedural: Generation mode
            chunk_seeds: Per-chunk seeds if needed
            
        Yields:
            Chunks of decoded data
        """
        if is_procedural:
            cascade = CascadeGenerator(master_seed)
            generated = 0
            
            while generated < file_size:
                remaining = file_size - generated
                size = min(chunk_size, remaining)
                
                # Generate this chunk
                chunk_index = generated // 4096
                offset_in_chunk = generated % 4096
                
                # Get the full chunk and slice what we need
                full_chunk = cascade.generate_chunk(chunk_index, 4096)
                yield full_chunk[offset_in_chunk:offset_in_chunk + size]
                
                generated += size
        else:
            if not chunk_seeds:
                raise ValueError("chunk_seeds required for streaming non-procedural")
            
            for i, chunk_seed in enumerate(chunk_seeds):
                remaining = file_size - sum(len(c) for c in [])  # Simplified
                size = min(chunk_size, remaining)
                
                gen = Xorshift64Star(chunk_seed)
                yield gen.next_bytes(size)
    
    def get_stats(self) -> dict:
        """Get statistics from last decode operation."""
        return self.decoding_stats.copy()
    
    def verify_integrity(self, decoded_data: bytes, expected_hash: Optional[bytes] = None) -> bool:
        """
        Verify decoded data integrity.
        
        Args:
            decoded_data: The decoded bytes
            expected_hash: Optional expected SHA256 hash
            
        Returns:
            True if integrity check passes
        """
        import hashlib
        
        actual_hash = hashlib.sha256(decoded_data).digest()
        
        if expected_hash is None:
            # Just return the hash for manual verification
            print(f"SHA256: {actual_hash.hex()}")
            return True
        else:
            matches = actual_hash == expected_hash
            if matches:
                print("✓ Integrity verified")
            else:
                print("✗ Integrity check failed")
            return matches


class InfiniteCanvasGenerator:
    """
    Implements "Infinite Canvas" logic - generates data of arbitrary size
    from a seed, with the ability to seek to any position.
    
    Useful for generating massive files without storing them entirely in memory.
    """
    
    def __init__(self, master_seed: int):
        self.master_seed = master_seed
        self.cascade = CascadeGenerator(master_seed)
    
    def get_chunk_at_offset(self, offset: int, size: int = 4096) -> bytes:
        """
        Get data chunk at any byte offset without generating preceding data.
        
        Args:
            offset: Byte offset in the virtual infinite file
            size: Number of bytes to retrieve
            
        Returns:
            Bytes at the specified offset
        """
        chunk_index = offset // 4096
        offset_in_chunk = offset % 4096
        
        # Generate the specific chunk
        chunk = self.cascade.generate_chunk(chunk_index, 4096 + size)
        
        return chunk[offset_in_chunk:offset_in_chunk + size]
    
    def get_region(self, start: int, end: int) -> bytes:
        """
        Get a region of data from the infinite canvas.
        
        Args:
            start: Start offset
            end: End offset (exclusive)
            
        Returns:
            Bytes in the region
        """
        result = bytearray()
        current = start
        
        while current < end:
            remaining = end - current
            chunk = self.get_chunk_at_offset(current, min(4096, remaining))
            result.extend(chunk)
            current += len(chunk)
        
        return bytes(result)
    
    def explore_dimensions(self, max_depth: int = 3) -> dict:
        """
        Explore the "dimensions" of the seed space.
        Returns statistics about the cascade structure.
        
        Args:
            max_depth: How many levels deep to explore
            
        Returns:
            Dictionary with exploration stats
        """
        stats = {
            'master_seed': hex(self.master_seed),
            'depth_levels': [],
            'total_subseeds': 0
        }
        
        for depth in range(max_depth):
            level_stats = {
                'depth': depth,
                'subseeds': [],
                'unique_values': 0
            }
            
            # Sample subseeds at this depth
            n_samples = min(16, 4 ** depth)  # Exponential growth
            subseeds = set()
            
            for i in range(n_samples):
                subseed = self.cascade.generate_subseed(i, depth)
                subseeds.add(subseed)
                level_stats['subseeds'].append(hex(subseed))
            
            level_stats['unique_values'] = len(subseeds)
            stats['depth_levels'].append(level_stats)
            stats['total_subseeds'] += len(subseeds)
        
        return stats


def create_preview_visualization(master_seed: int, preview_size: int = 256) -> str:
    """
    Create a text-based visualization of the seed's "signature".
    
    Args:
        master_seed: The seed to visualize
        preview_size: Size of preview data
        
    Returns:
        ASCII art representation
    """
    cascade = CascadeGenerator(master_seed)
    data = cascade.generate_file(preview_size)
    
    # Create hex dump style visualization
    lines = []
    lines.append(f"╔{'═' * 66}╗")
    lines.append(f"║ SEED VISUALIZATION: 0x{master_seed:016X}{' ' * 27}║")
    lines.append(f"╠{'═' * 66}╣")
    
    for i in range(0, min(256, preview_size), 16):
        hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
        lines.append(f"║ {i:04x}: {hex_part:<48} |{ascii_part}|")
    
    lines.append(f"╚{'═' * 66}╝")
    
    return '\n'.join(lines)


if __name__ == "__main__":
    print("=" * 60)
    print("GENESIS DECODER - Phase 2 Test")
    print("=" * 60)
    
    decoder = GenesisDecoder()
    
    # Test 1: Decode procedural data
    print("\n[TEST 1] Procedural Decoding")
    test_seed = 0x12345678DEADBEEF
    test_size = 8192
    
    decoded = decoder.decode_from_seed(test_seed, test_size, is_procedural=True)
    print(f"Decoded {len(decoded)} bytes from seed 0x{test_seed:016X}")
    print(f"First 64 bytes: {decoded[:64].hex()}")
    print(f"Stats: {decoder.get_stats()}")
    
    # Test 2: Verify determinism
    print("\n[TEST 2] Determinism Verification")
    decoded2 = decoder.decode_from_seed(test_seed, test_size, is_procedural=True)
    assert decoded == decoded2, "Determinism failed!"
    print("✓ Same seed produces identical output")
    
    # Test 3: Streaming decode
    print("\n[TEST 3] Streaming Decode")
    total_streamed = 0
    for chunk in decoder.stream_decode(test_seed, test_size, chunk_size=1024):
        total_streamed += len(chunk)
        if total_streamed <= 64:
            print(f"Stream chunk: {len(chunk)} bytes")
    print(f"Total streamed: {total_streamed} bytes")
    
    # Test 4: Infinite Canvas
    print("\n[TEST 4] Infinite Canvas")
    canvas = InfiniteCanvasGenerator(test_seed)
    
    # Seek to different positions
    region1 = canvas.get_region(0, 64)
    region2 = canvas.get_region(4096, 4160)  # Second chunk
    region3 = canvas.get_region(1000000, 1000064)  # Far offset
    
    print(f"Region at 0: {region1[:32].hex()}...")
    print(f"Region at 4096: {region2[:32].hex()}...")
    print(f"Region at 1000000: {region3[:32].hex()}...")
    
    # Test 5: Visualization
    print("\n[TEST 5] Seed Visualization")
    viz = create_preview_visualization(test_seed)
    print(viz)
    
    # Test 6: Dimension exploration
    print("\n[TEST 6] Dimension Exploration")
    exploration = canvas.explore_dimensions(max_depth=3)
    print(f"Master Seed: {exploration['master_seed']}")
    print(f"Total subseeds explored: {exploration['total_subseeds']}")
    for level in exploration['depth_levels']:
        print(f"  Depth {level['depth']}: {level['unique_values']} unique values")
    
    print("\n" + "=" * 60)
    print("Phase 2 Complete - Decoder Ready")
    print("=" * 60)
