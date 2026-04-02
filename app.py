"""
app.py - Phase 4: The Interface (The Portal)

Minimalist, high-tech Streamlit UI for the Genesis Protocol.
Features:
- File encoding to seed representation
- Seed decoding back to files
- Real-time cascade visualization
- Statistics and analytics
"""

import streamlit as st
import numpy as np
import time
import hashlib
from pathlib import Path
from io import BytesIO

from genesis_core import CascadeGenerator, calculate_entropy
from genesis_decoder import create_preview_visualization
from genesis_encoder import GenesisEncoder, EncodingResult
from genesis_decoder import GenesisDecoder, InfiniteCanvasGenerator


# Page configuration
st.set_page_config(
    page_title="Genesis Protocol",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for high-tech vibe
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        background: linear-gradient(90deg, #00C9FF 0%, #92FE9D 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .seed-display {
        font-family: 'Courier New', monospace;
        font-size: 1.1rem;
        background: #1e1e1e;
        padding: 0.5rem;
        border-radius: 5px;
        word-break: break-all;
    }
    .cascade-animation {
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.5; }
        100% { opacity: 1; }
    }
</style>
""", unsafe_allow_html=True)


def visualize_cascade_tree(master_seed: int, max_depth: int = 3):
    """Create a text-based visualization of the cascade tree."""
    cascade = CascadeGenerator(master_seed)
    
    tree_viz = []
    tree_viz.append(f"🌱 Master Seed: 0x{master_seed:016X}")
    tree_viz.append("│")
    
    for depth in range(max_depth):
        n_nodes = min(4, 2 ** depth)
        indent = "│   " * depth
        
        for i in range(n_nodes):
            subseed = cascade.generate_subseed(i, depth)
            is_last = (i == n_nodes - 1)
            branch = "└──" if is_last else "├──"
            tree_viz.append(f"{indent}{branch} Depth {depth}, Index {i}: 0x{subseed:08X}")
            
            if depth < max_depth - 1 and not is_last:
                tree_viz.append(f"{indent}│")
        
        if depth < max_depth - 1:
            tree_viz.append("│")
    
    return "\n".join(tree_viz)


def animate_generation(progress_bar, status_text, target_chunks: int):
    """Animate the cascade generation process."""
    for i in range(target_chunks):
        progress = (i + 1) / target_chunks
        progress_bar.progress(progress)
        status_text.text(f"Generating chunk {i + 1}/{target_chunks}...")
        time.sleep(0.05)  # Simulate work


def main():
    # Header
    st.markdown('<h1 class="main-header">🌱 GENESIS PROTOCOL</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Deterministic Procedural File Generator</p>', unsafe_allow_html=True)
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    mode = st.sidebar.radio(
        "Select Mode",
        ["Encode File → Seed", "Decode Seed → File", "Cascade Explorer", "About"]
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Quick Stats**")
    st.sidebar.info("Files encoded: 0\nSeeds generated: 0\nData compressed: 0 MB")
    
    # Mode: Encode
    if mode == "Encode File → Seed":
        st.header("📤 Encoder Module")
        st.write("Transform any file into its mathematical essence - a Master Seed.")
        
        uploaded_file = st.file_uploader(
            "Choose a file to encode",
            type=None,  # Accept all types
            help="Smaller files encode faster. Large random files will use cascade tree mode."
        )
        
        max_search = st.slider(
            "Max Seed Search Attempts",
            min_value=1000,
            max_value=100000,
            value=10000,
            step=1000,
            help="Higher values increase chance of finding procedural match but take longer"
        )
        
        if uploaded_file and st.button("🚀 Start Encoding", type="primary"):
            with st.spinner("Analyzing file entropy..."):
                file_bytes = uploaded_file.read()
                file_size = len(file_bytes)
                entropy = calculate_entropy(file_bytes)
                
                st.metric("File Size", f"{file_size:,} bytes")
                st.metric("Entropy", f"{entropy:.3f} bits/byte", 
                         delta="LOW" if entropy < 4.0 else "MEDIUM" if entropy < 6.5 else "HIGH")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            encoder = GenesisEncoder(max_search_seeds=max_search)
            
            with st.spinner("Encoding in progress..."):
                result = encoder.encode_file(file_bytes, verbose=False)
                
                # Animate based on chunk count
                chunks = result.metadata[17:21] if result.metadata else b'\x00\x00\x00\x01'
                import struct
                try:
                    n_chunks = struct.unpack('<Q', result.metadata[17:25])[0]
                except:
                    n_chunks = 1
                # animate_generation(progress_bar, status_text, min(n_chunks, 20))
                progress_bar.progress(1.0)
            
            # Results
            st.success("✅ Encoding Complete!")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Compression Ratio", f"{result.compression_ratio:.2%}")
            with col2:
                st.metric("Procedural", "Yes" if result.is_procedural else "No")
            with col3:
                st.metric("Master Seed", f"0x{result.master_seed:08X}...")
            
            st.subheader("🎯 Master Seed")
            seed_hex = f"0x{result.master_seed:016X}"
            st.code(seed_hex, language="text")
            
            st.download_button(
                label="📥 Download Seed File",
                data=result.metadata,
                file_name=f"{uploaded_file.name}.genesis",
                mime="application/octet-stream"
            )
            
            # Visualization
            with st.expander("🌳 View Cascade Tree"):
                st.text(visualize_cascade_tree(result.master_seed))
    
    # Mode: Decode
    elif mode == "Decode Seed → File":
        st.header("📥 Decoder Module")
        st.write("Expand a tiny seed into its full file manifestation.")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            seed_input = st.text_input(
                "Master Seed (hex)",
                placeholder="0x12345678DEADBEEF",
                help="Enter the master seed value"
            )
            
            file_size = st.number_input(
                "Output File Size (bytes)",
                min_value=1,
                max_value=100 * 1024 * 1024,  # 100MB max
                value=4096,
                step=1024
            )
            
            is_procedural = st.checkbox("Procedural Mode", value=True,
                                       help="If checked, generates purely from seed. If unchecked, requires chunk seeds.")
        
        with col2:
            st.markdown("### Preview")
            if seed_input:
                try:
                    seed_val = int(seed_input, 16)
                    viz = create_preview_visualization(seed_val, preview_size=128)
                    st.text(viz)
                except:
                    st.warning("Invalid hex seed")
        
        if st.button("🌀 Generate File", type="primary"):
            if seed_input:
                try:
                    master_seed = int(seed_input, 16)
                    
                    decoder = GenesisDecoder()
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    with st.spinner("Expanding seed universe..."):
                        # animate_generation(progress_bar, status_text, file_size // 4096)
                        decoded_data = decoder.decode_from_seed(
                            master_seed, file_size, is_procedural
                        )
                        progress_bar.progress(1.0)
                    
                    st.success(f"✅ Generated {len(decoded_data)} bytes!")
                    
                    stats = decoder.get_stats()
                    st.metric("Generation Time", f"{stats['time_seconds']:.3f}s")
                    st.metric("Throughput", f"{stats['throughput_mbs']:.1f} MB/s")
                    
                    st.download_button(
                        label="💾 Download Generated File",
                        data=decoded_data,
                        file_name="genesis_output.bin",
                        mime="application/octet-stream"
                    )
                    
                    # Show first bytes
                    with st.expander("📊 Data Preview"):
                        st.write("**First 256 bytes (hex):**")
                        st.text(decoded_data[:256].hex())
                        
                except Exception as e:
                    st.error(f"Decoding failed: {str(e)}")
            else:
                st.warning("Please enter a seed value")
    
    # Mode: Explorer
    elif mode == "Cascade Explorer":
        st.header("🔬 Cascade Explorer")
        st.write("Explore the mathematical structure of seed space.")
        
        seed_input = st.text_input("Enter a seed to explore:", value="0xDEADBEEF12345678")
        
        if seed_input:
            try:
                master_seed = int(seed_input, 16)
                cascade = CascadeGenerator(master_seed)
                canvas = InfiniteCanvasGenerator(master_seed)
                
                # Tabs for different views
                tab1, tab2, tab3, tab4 = st.tabs([
                    "Tree Structure", "Dimension Analysis", "Infinite Canvas", "Signature"
                ])
                
                with tab1:
                    st.subheader("Cascade Tree Visualization")
                    depth = st.slider("Tree Depth", 1, 5, 3)
                    st.text(visualize_cascade_tree(master_seed, max_depth=depth))
                
                with tab2:
                    st.subheader("Dimension Analysis")
                    exploration = canvas.explore_dimensions(max_depth=4)
                    
                    st.json({
                        'master_seed': exploration['master_seed'],
                        'total_subseeds': exploration['total_subseeds'],
                        'levels': len(exploration['depth_levels'])
                    })
                    
                    for level in exploration['depth_levels']:
                        st.metric(f"Depth {level['depth']}", 
                                 f"{level['unique_values']} unique values")
                
                with tab3:
                    st.subheader("Infinite Canvas Seek Test")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        offset1 = st.number_input("Offset 1", value=0, step=64)
                        region1 = canvas.get_region(offset1, offset1 + 64)
                        st.code(region1.hex(), language="text")
                    
                    with col2:
                        offset2 = st.number_input("Offset 2", value=4096, step=64)
                        region2 = canvas.get_region(offset2, offset2 + 64)
                        st.code(region2.hex(), language="text")
                    
                    # Verify determinism
                    region1_again = canvas.get_region(offset1, offset1 + 64)
                    if region1 == region1_again:
                        st.success("✓ Deterministic: Same offset produces identical data")
                
                with tab4:
                    st.subheader("Seed Signature")
                    viz = create_preview_visualization(master_seed, preview_size=256)
                    st.text(viz)
                    
                    # Hash fingerprint
                    test_data = cascade.generate_file(1024)
                    fingerprint = hashlib.sha256(test_data).hexdigest()[:16]
                    st.info(f"Fingerprint: {fingerprint}")
                    
            except Exception as e:
                st.error(f"Invalid seed: {str(e)}")
    
    # Mode: About
    elif mode == "About":
        st.header("📖 About Genesis Protocol")
        
        st.markdown("""
        ### The Philosophy
        
        The Genesis Protocol is a **Deterministic Procedural File Generator** inspired by:
        - 🎮 No Man's Sky's universe generation
        - ⛏️ Minecraft's world seeds
        - 🔐 Cryptographic hash functions
        - 📊 Information theory
        
        ### How It Works
        
        1. **The Encoder (Archaeologist)**
           - Analyzes file entropy
           - For low-entropy files: Searches for matching procedural seed
           - For high-entropy files: Creates a cascade tree of subseeds
        
        2. **The Decoder (Genesis Machine)**
           - Takes a Master Seed
           - Expands it recursively: Master → Subseeds → Chunks → File
           - Supports streaming for massive files
        
        3. **The Mathematics**
           - Uses Xorshift64* PRNG for deterministic randomness
           - SHA256 for seed mixing and verification
           - Addresses Pigeonhole Principle via cascade trees
        
        ### Mathematical Reality Check
        
        Due to the **Pigeonhole Principle**, it's impossible to compress arbitrary 
        random data into a small seed. The system handles this by:
        
        - ✅ Perfect compression for procedural/low-entropy files
        - ⚠️ Cascade tree representation for high-entropy files
        - 🔍 Optimized search for finding procedural matches
        
        ### Technical Stack
        
        - Python 3.x
        - NumPy for entropy calculations
        - Streamlit for the interface
        - hashlib for cryptographic operations
        """)
        
        st.markdown("---")
        st.markdown("**Version:** 1.0.0 | **Built with** ❤️ **by Digital Alchemist Architect**")


if __name__ == "__main__":
    main()
