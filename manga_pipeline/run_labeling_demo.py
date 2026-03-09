#!/usr/bin/env python3
"""
Demo script showing the complete manual labeling workflow
"""

import os
import sys
from pathlib import Path
import subprocess
import time

def run_command(cmd, description):
    """Run a command and show progress"""
    print(f"\n🎬 {description}")
    print(f"   Command: {cmd}")
    
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True,
            cwd=Path(__file__).parent
        )
        
        if result.returncode == 0:
            print("   ✅ Success")
            if result.stdout.strip():
                print(f"   Output: {result.stdout.strip()}")
        else:
            print(f"   ❌ Error: {result.stderr.strip()}")
            
    except Exception as e:
        print(f"   ❌ Exception: {e}")

def main():
    print("📚 Manga Factory Data Labeling Demo")
    print("="*50)
    
    print("\nThis demo shows the complete workflow for enhancing the data labeling system:")
    print("1. Prepare a labeling session")
    print("2. Use the manual labeling tool")
    print("3. Manage and validate labeled data")
    print("4. Integrate with the ML pipeline")
    
    while True:
        print("\n📋 Select an option:")
        print("1. Prepare a new labeling session")
        print("2. Launch manual labeling tool")
        print("3. Analyze existing training data")
        print("4. Validate annotations")
        print("5. Generate statistics report")
        print("6. Visualize data distribution")
        print("7. Integrate manual labels")
        print("8. Train ML model (if sufficient data)")
        print("9. Run complete demo workflow")
        print("0. Exit")
        
        choice = input("\nEnter your choice (0-9): ").strip()
        
        if choice == "0":
            print("👋 Exiting demo")
            break
        elif choice == "1":
            run_command(
                "python integrate_manual_labels.py --prepare-session",
                "Preparing a new labeling session"
            )
        elif choice == "2":
            print("\n🎬 Launching manual labeling tool...")
            print("   Close the labeling window when done")
            try:
                subprocess.run([
                    sys.executable, 
                    str(Path(__file__).parent / "manual_labeling_tool.py")
                ], cwd=Path(__file__).parent)
            except Exception as e:
                print(f"   ❌ Error launching tool: {e}")
        elif choice == "3":
            run_command(
                "python data_labeling_manager.py --scan",
                "Scanning training data"
            )
        elif choice == "4":
            run_command(
                "python data_labeling_manager.py --validate",
                "Validating annotations"
            )
        elif choice == "5":
            run_command(
                "python data_labeling_manager.py --report",
                "Generating statistics report"
            )
        elif choice == "6":
            output_file = f"./data_distribution_{int(time.time())}.png"
            run_command(
                f"python data_labeling_manager.py --visualize {output_file}",
                f"Visualizing data distribution to {output_file}"
            )
        elif choice == "7":
            print("\n💡 To integrate manual labels, specify the directory containing your labeled data:")
            label_dir = input("   Enter path to labeled data directory: ").strip()
            if label_dir:
                run_command(
                    f"python integrate_manual_labels.py --integrate {label_dir}",
                    f"Integrating labels from {label_dir}"
                )
        elif choice == "8":
            run_command(
                "python integrate_manual_labels.py --train-model",
                "Training ML model with available data"
            )
        elif choice == "9":
            print("\n🎬 Running complete demo workflow...")
            
            # Prepare session
            run_command(
                "python integrate_manual_labels.py --prepare-session --session-dir ./demo_session",
                "1. Preparing demo session"
            )
            
            # Scan existing data
            run_command(
                "python data_labeling_manager.py --scan",
                "2. Scanning existing training data"
            )
            
            # Validate existing data
            run_command(
                "python data_labeling_manager.py --validate",
                "3. Validating existing annotations"
            )
            
            # Generate report
            run_command(
                "python data_labeling_manager.py --report",
                "4. Generating statistics report"
            )
            
            print("\n🎉 Complete demo workflow finished!")
            print("\n💡 Note: To use the manual labeling tool, run:")
            print("   python manual_labeling_tool.py")
            print("\n💡 To integrate your own labels, place them in a directory and run:")
            print("   python integrate_manual_labels.py --integrate /path/to/your/labels")
        else:
            print("❌ Invalid choice. Please enter 0-9.")

if __name__ == "__main__":
    main()