#!/usr/bin/env python3
"""Test Python 3.13 compatibility for boneio package."""

import importlib
import pkgutil
import sys


def test_imports():
    """Test all boneio submodules for import errors."""
    print(f"Python version: {sys.version}\n")
    print("=" * 70)
    print("Testing module imports...")
    print("=" * 70)
    
    import boneio
    
    errors = []
    success = []
    
    for importer, modname, ispkg in pkgutil.walk_packages(
        path=boneio.__path__, 
        prefix='boneio.',
        onerror=lambda x: None
    ):
        try:
            importlib.import_module(modname)
            success.append(modname)
            print(f"✓ {modname}")
        except PermissionError as e:
            # Ignore hardware access errors during testing
            success.append(modname)
            print(f"⚠ {modname}: PermissionError (hardware access - OK for testing) {e}")
        except (ImportError, OSError) as e:
            # Ignore hardware-related import errors (Adafruit_BBIO, GPIO, etc.)
            if "nvmem" in str(e) or "GPIO" in str(e) or "gpiochip" in str(e):
                success.append(modname)
                print(f"⚠ {modname}: Hardware access error (OK for testing)")
            else:
                errors.append((modname, type(e).__name__, str(e)))
                print(f"✗ {modname}: {type(e).__name__}: {e}")
        except Exception as e:
            errors.append((modname, type(e).__name__, str(e)))
            print(f"✗ {modname}: {type(e).__name__}: {e}")
    
    print("\n" + "=" * 70)
    print(f"Summary: {len(success)} OK, {len(errors)} FAILED")
    print("=" * 70)
    
    if errors:
        print("\nFailed modules:")
        for modname, exc_type, exc_msg in errors:
            print(f"  - {modname}")
            print(f"    {exc_type}: {exc_msg[:100]}")
    
    return errors


def check_deprecated_imports():
    """Check for deprecated import patterns."""
    print("\n" + "=" * 70)
    print("Checking for deprecated import patterns...")
    print("=" * 70)
    
    import subprocess
    
    patterns = [
        ("collections.Mapping", "from collections import.*Mapping"),
        ("collections.Sequence", "from collections import.*Sequence"),
        ("collections.Iterable", "from collections import.*Iterable"),
        ("collections.MutableMapping", "from collections import.*MutableMapping"),
        ("asyncio.coroutine", "@asyncio.coroutine"),
    ]
    
    issues = []
    for name, pattern in patterns:
        try:
            result = subprocess.run(
                ["grep", "-r", "-n", pattern, "boneio/", "--include=*.py"],
                capture_output=True,
                text=True
            )
            if result.stdout:
                issues.append((name, result.stdout))
                print(f"\n⚠ Found deprecated: {name}")
                for line in result.stdout.split('\n')[:5]:  # Show first 5
                    if line:
                        print(f"  {line}")
        except Exception as e:
            print(f"Error checking {name}: {e}")
    
    if not issues:
        print("✓ No deprecated import patterns found")
    
    return issues


if __name__ == "__main__":
    print("BoneIO Python 3.13 Compatibility Test")
    print("=" * 70)
    
    # Test imports
    import_errors = test_imports()
    
    # Check deprecated patterns
    deprecated = check_deprecated_imports()
    
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"Import errors: {len(import_errors)}")
    print(f"Deprecated patterns: {len(deprecated)}")
    
    if import_errors or deprecated:
        print("\n⚠ Action required - see details above")
        sys.exit(1)
    else:
        print("\n✓ All checks passed!")
        sys.exit(0)
