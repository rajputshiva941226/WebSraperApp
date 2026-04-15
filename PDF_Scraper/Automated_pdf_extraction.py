#!/usr/bin/env python3
"""
COMPLETE AUTOMATED PDF EXTRACTION SYSTEM FOR WINDOWS
Integrates Docker management + modular PDF extraction

Usage:
    python automated_extraction.py input.pdf
    python automated_extraction.py pdf_folder/
    python automated_extraction.py input.pdf --no-grobid --cleanup
"""

import sys
import time
import subprocess
import urllib.request
import winreg
import os
from pathlib import Path

# Import the extraction module (must be in same directory or PYTHONPATH)
try:
    from pdf_extraction_module import (
        ExtractionConfig, PDFAuthorExtractor
    )
except ImportError:
    print("❌ Error: pdf_extraction_module.py not found!")
    print("Make sure pdf_extraction_module.py is in the same directory.")
    sys.exit(1)

try:
    from grobid_client.grobid_client import GrobidClient
    GROBID_CLIENT_AVAILABLE = True
except ImportError:
    GROBID_CLIENT_AVAILABLE = False


# ==================== DOCKER MANAGER ====================
class DockerManager:
    """Fully automated Docker and GROBID management for Windows"""
    
    DOCKER_URL = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
    GROBID_IMAGE = "lfoppiano/grobid:0.8.0"
    CONTAINER_NAME = "grobid-server"
    
    def __init__(self, port=8070):
        self.port = port
    
    def is_docker_installed(self):
        """Check if Docker Desktop is installed"""
        try:
            subprocess.run(["docker", "--version"], capture_output=True, timeout=5)
            return True
        except:
            pass
        
        try:
            winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                          r"SOFTWARE\Docker Inc.\Docker\1.0", 0, winreg.KEY_READ)
            return True
        except:
            return False
    
    def install_docker(self):
        """Download and install Docker Desktop"""
        print("\n" + "="*70)
        print("🐳 DOCKER DESKTOP INSTALLATION REQUIRED")
        print("="*70)
        print("\nDocker Desktop is needed to run GROBID.")
        print("This script will download and install it (~500 MB).")
        print("\n⚠️  Requirements:")
        print("  • Administrator privileges")
        print("  • System restart after installation")
        
        if input("\nContinue? (yes/no): ").lower() not in ['yes', 'y']:
            print("Installation cancelled")
            return False
        
        installer = Path(os.environ['TEMP']) / "DockerInstaller.exe"
        
        try:
            print("\n📥 Downloading Docker Desktop...")
            urllib.request.urlretrieve(self.DOCKER_URL, installer,
                lambda b, bs, t: print(f"\r   Progress: {min(100, int(b*bs*100/t))}%", end=''))
            print("\n✅ Download complete")
            
            print("\n🔧 Installing (this takes 5-10 minutes)...")
            subprocess.run(['powershell', '-Command',
                          f'Start-Process "{installer}" -ArgumentList "install --quiet" -Verb RunAs -Wait'])
            
            installer.unlink()
            print("\n✅ Installation complete!")
            print("\n⚠️  RESTART REQUIRED")
            print("Please restart your computer and run this script again.")
            input("\nPress Enter to exit...")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            if installer.exists():
                installer.unlink()
            return False
    
    def is_docker_running(self):
        """Check if Docker Engine is running"""
        try:
            subprocess.run(["docker", "info"], capture_output=True, timeout=5, check=True)
            return True
        except:
            return False
    
    def start_docker(self):
        """Start Docker Desktop"""
        print("\n🚀 Starting Docker Desktop...")
        
        docker_exe = None
        for path in [r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
                     os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe")]:
            if os.path.exists(path):
                docker_exe = path
                break
        
        if not docker_exe:
            print("❌ Docker Desktop not found")
            return False
        
        try:
            subprocess.Popen([docker_exe], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            
            print("⏳ Waiting for Docker Engine (30-60 seconds)...")
            for i in range(120):
                time.sleep(1)
                if self.is_docker_running():
                    print(f"✅ Docker ready! ({i+1}s)")
                    return True
                if i % 15 == 0 and i > 0:
                    print(f"   Still waiting... ({i}s)")
            
            print("\n⚠️  Docker starting but taking longer. Please wait and retry.")
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def is_container_running(self):
        """Check if GROBID container is running"""
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.CONTAINER_NAME}"],
                capture_output=True, text=True, timeout=10)
            return bool(result.stdout.strip())
        except:
            return False
    
    def pull_and_start_grobid(self):
        """Pull GROBID image and start container"""
        print(f"\n📦 Setting up GROBID container...")
        
        # Stop existing container
        if self.is_container_running():
            print("   Stopping old container...")
            subprocess.run(["docker", "stop", self.CONTAINER_NAME],
                          capture_output=True, timeout=30)
            subprocess.run(["docker", "rm", self.CONTAINER_NAME],
                          capture_output=True, timeout=10)
        
        # Check if image exists
        result = subprocess.run(["docker", "images", "-q", self.GROBID_IMAGE],
                               capture_output=True, text=True, timeout=10)
        
        if not result.stdout.strip():
            print(f"📥 Pulling GROBID image (~1.5 GB, first time only)...")
            process = subprocess.Popen(["docker", "pull", self.GROBID_IMAGE],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, bufsize=1)
            for line in process.stdout:
                if "Status:" in line or "Download" in line:
                    print(f"   {line.strip()}")
            process.wait()
            
            if process.returncode != 0:
                print("❌ Failed to pull image")
                return False
            print("✅ Image downloaded")
        
        # Start container
        print(f"🚀 Starting GROBID on port {self.port}...")
        result = subprocess.run(
            ["docker", "run", "-d", "--rm", "--init", "--ulimit", "core=0",
             "-p", f"{self.port}:8070", "--name", self.CONTAINER_NAME,
             self.GROBID_IMAGE],
            capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"❌ Failed to start: {result.stderr}")
            return False
        
        # Wait for health check
        print("⏳ Waiting for GROBID to initialize...")
        for i in range(60):
            time.sleep(2)
            try:
                response = urllib.request.urlopen(
                    f"http://localhost:{self.port}/api/isalive", timeout=2)
                if response.status == 200:
                    print(f"✅ GROBID ready! ({(i+1)*2}s)")
                    return True
            except:
                pass
        
        print("⚠️  Container started but not responding. Continuing...")
        return True
    
    def ensure_ready(self):
        """Main setup orchestration - returns True if GROBID is ready"""
        print("\n" + "="*70)
        print("🔍 CHECKING DOCKER & GROBID STATUS")
        print("="*70)
        
        # Check installation
        if not self.is_docker_installed():
            print("❌ Docker not installed")
            return self.install_docker()
        print("✅ Docker installed")
        
        # Check if running
        if not self.is_docker_running():
            print("⚠️  Docker not running")
            if not self.start_docker():
                return False
        else:
            print("✅ Docker running")
        
        # Check GROBID
        if self.is_container_running():
            print(f"✅ GROBID already running on port {self.port}")
            return True
        
        print("⚠️  GROBID not running")
        return self.pull_and_start_grobid()
    
    def stop_grobid(self):
        """Stop GROBID container"""
        if self.is_container_running():
            print("\n🛑 Stopping GROBID...")
            subprocess.run(["docker", "stop", self.CONTAINER_NAME],
                          capture_output=True, timeout=30)
            print("✅ GROBID stopped")


# ==================== MAIN ENTRY POINT ====================
def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Automated PDF Author Extraction with Docker/GROBID Management"
    )
    parser.add_argument('pdf_path', help='PDF file or directory')
    parser.add_argument('--no-grobid', action='store_true', 
                       help='Skip GROBID, use only PyMuPDF methods')
    parser.add_argument('--cleanup', action='store_true',
                       help='Clean up temporary files after processing')
    parser.add_argument('--stop-grobid', action='store_true',
                       help='Stop GROBID container after processing')
    parser.add_argument('--output-dir', default='output',
                       help='Output directory (default: output)')
    parser.add_argument('--grobid-port', type=int, default=8070,
                       help='GROBID port (default: 8070)')
    args = parser.parse_args()
    
    print("="*70)
    print("📄 AUTOMATED PDF AUTHOR EXTRACTION SYSTEM")
    print("="*70)
    
    # ==================== DOCKER SETUP ====================
    docker = DockerManager(port=args.grobid_port)
    grobid_ready = False
    
    if not args.no_grobid:
        grobid_ready = docker.ensure_ready()
        if not grobid_ready:
            print("\n⚠️  GROBID setup failed. Continuing with PyMuPDF methods only...")
            time.sleep(2)
    else:
        print("\n⚠️  GROBID disabled (--no-grobid flag)")
    
    # ==================== EXTRACTION SETUP ====================
    print("\n" + "="*70)
    print("🔄 INITIALIZING EXTRACTION SYSTEM")
    print("="*70)
    
    # Initialize config
    config = ExtractionConfig(output_dir=args.output_dir)
    
    # Initialize GROBID client if available
    grobid_client = None
    if grobid_ready and GROBID_CLIENT_AVAILABLE:
        try:
            grobid_client = GrobidClient(grobid_server=f"http://localhost:{args.grobid_port}")
            print(f"✅ GROBID client initialized (port {args.grobid_port})")
        except Exception as e:
            print(f"⚠️  GROBID client initialization failed: {e}")
    
    # Initialize extractor
    extractor = PDFAuthorExtractor(config=config, grobid_client=grobid_client)
    
    # ==================== PDF PROCESSING ====================
    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"❌ Path not found: {pdf_path}")
        return 1
    
    print(f"\n📂 Input: {pdf_path}")
    print(f"🎯 GROBID: {'Enabled' if grobid_ready else 'Disabled'}")
    print(f"📁 Output: {config.output_dir}")
    
    try:
        total_pdfs = 0
        total_authors_all = 0
        
        # Process single file or directory
        if pdf_path.is_file():
            total_authors, stats = extractor.process_pdf(pdf_path)
            total_pdfs = 1
            total_authors_all = total_authors
        elif pdf_path.is_dir():
            pdf_files = sorted(pdf_path.glob('*.pdf'))
            total_pdfs = len(pdf_files)
            print(f"\n📚 Found {total_pdfs} PDF file(s)")
            
            for idx, pdf_file in enumerate(pdf_files, 1):
                print(f"\n[PDF {idx}/{total_pdfs}]")
                total_authors, stats = extractor.process_pdf(pdf_file)
                total_authors_all += total_authors
        else:
            print(f"❌ Invalid path: {pdf_path}")
            return 1
        
        # ==================== FINAL SUMMARY ====================
        print("\n" + "="*70)
        print("✅ EXTRACTION COMPLETE!")
        print("="*70)
        print(f"\n📊 Summary:")
        print(f"  • PDFs processed: {total_pdfs}")
        print(f"  • Total authors extracted: {total_authors_all}")
        print(f"  • Output directory: {config.output_dir}")
        
        # Cleanup
        if args.cleanup:
            print("\n🧹 Cleaning up temporary files...")
            extractor.cleanup()
            print("✅ Cleanup complete")
        
        # Stop GROBID
        if args.stop_grobid and grobid_ready:
            docker.stop_grobid()
        
        print("\n" + "="*70)
        print("🎉 ALL DONE!")
        print("="*70)
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
        if args.stop_grobid and grobid_ready:
            docker.stop_grobid()
        return 1
    except Exception as e:
        print(f"\n❌ Error during extraction: {e}")
        import traceback
        traceback.print_exc()
        if args.stop_grobid and grobid_ready:
            docker.stop_grobid()
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)