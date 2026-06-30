# Copyright 2026 Roland Rosier
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# see the License for the specific language governing permissions and
# limitations under the License.

"""Pytest configuration for the MeshCore LoRa project."""

import sys
import os
from pathlib import Path

# Add the project root to the Python path
#sys.path.insert(0, str(Path(__file__).parent.parent))
current_dir = os.path.abspath(os.path.dirname(__file__))
# project_root = os.path.abspath(os.path.join(current_dir, '..'))
project_root = os.path.abspath(os.path.join(current_dir, '..', 'src'))

if project_root not in sys.path:
    sys.path.append(project_root)
    print(f"✅ Added project root to sys.path: {project_root}")
