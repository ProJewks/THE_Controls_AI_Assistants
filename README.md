# NOTICE:
This is a **v35 edition** fork of the Studio 5000 AI Assistant, maintained independently. It defaults to Studio 5000 Logix Designer **v35**, but supports any installed version through the setup script's `--version` flag (see [Choosing your Studio 5000 version](#-choosing-your-studio-5000-version) below). Credit to the original project this was based on: [rivie13/studio5000-AI-Assistant](https://github.com/rivie13/studio5000-AI-Assistant) (v36 by default). This repo is a prototype — you're welcome to fork it and make it your own.

# 🤖 Studio 5000 AI-Powered PLC Programming Assistant

This revolutionary MCP (Model Context Protocol) server transforms PLC programming by providing AI-powered code generation, L5X routine creation, real .ACD file generation, and seamless Studio 5000 integration. Convert natural language specifications directly into working ladder logic and complete Studio 5000 projects!

## ⚡ **TL;DR - One Command Setup**
```bash
# 1. Get Python 3.12 (NOT 3.11!) from python.org
python --version  # Must show 3.12.x

# 2. Clone the repo
git clone https://github.com/ProJewks/THE_Studio5000_AI_Assistant_V35.git
cd THE_Studio5000_AI_Assistant_V35

# 3. Run the setup script — installs everything and writes your config for you
python setup.py
```
`setup.py` detects your installed Studio 5000 version (defaulting to v35), installs
`requirements.txt`, installs the Logix Designer SDK wheel if it finds one, generates
ready-to-use MCP config files with the correct paths for **your** machine, and runs the
built-in self-test. See [Choosing your Studio 5000 version](#-choosing-your-studio-5000-version)
if you're not on v35, and [What setup.py generates](#-what-setuppy-generates) for what to do
with the files it creates.

**That's it!** ✅ Skip to [Configuration for Claude Desktop](#configuration-for-claude-desktop) if
you want to wire it up by hand instead, or just point Claude Desktop/Claude Code at the files
`setup.py` already generated.

## 🔀 **Choosing your Studio 5000 version**

This fork defaults to **v35**, but you're not locked into it. `setup.py` scans your machine for
every installed Logix Designer version and lets you pick:

```bash
# Auto-detect and prompt interactively (default: v35 if present)
python setup.py

# Force a specific version, e.g. the upstream project's v36
python setup.py --version 36

# Non-interactive, accept every default (CI / scripted installs)
python setup.py --yes

# Skip prompts but still write straight into Claude Desktop's config
python setup.py --version 37 --write-claude-desktop --yes
```

If a version isn't auto-detected, the script falls back to the standard Rockwell install path
(`...\Logix Designer\ENU\v<N>\Bin\Help\ENU\rs5000`) for whatever number you give it — override
with `--doc-root` on the server itself (see [Step 5](#step-5-configure-environment-variables-advanced-users-only))
if your install lives somewhere non-standard.

## 📦 **What setup.py generates**

Every file below is machine-specific (absolute paths, your Python interpreter) and
git-ignored — regenerate them any time by re-running `python setup.py`:

| File | Used by |
|---|---|
| `mcp_config.local.json` | Generic/Cursor-style MCP config |
| `claude_desktop_config.snippet.json` | Paste under `"mcpServers"` in Claude Desktop's config (or let `--write-claude-desktop` do it for you) |
| `.mcp.json` | Claude Code project-scope MCP config — picked up automatically when you open this repo in Claude Code |

`mcp_config.json` (no `.local`) stays in the repo as a plain **template** for reference — don't
edit it by hand, run `setup.py` instead.

## 📚 **New Team Member Resources**

🎯 **Complete Team Guides Available:**
- 📖 **[TEAM_USAGE_GUIDE.md](TEAM_USAGE_GUIDE.md)** - Complete workflow guide with real examples
- ⚡ **[QUICK_REFERENCE_CARD.md](QUICK_REFERENCE_CARD.md)** - Daily commands and shortcuts  
- 🔧 **[TEAM_TROUBLESHOOTING_GUIDE.md](TEAM_TROUBLESHOOTING_GUIDE.md)** - Common issues and solutions
- 🗂️ **[PLC_COPILOT_PROJECT_TEMPLATE.md](PLC_COPILOT_PROJECT_TEMPLATE.md)** - How to set up a
  per-client "PLC Copilot" project folder (`CLAUDE.md` + reuse-library convention) on top of this
  server

## 🚀 **Quick Start for Teammates**

**Ready to use this tool? Follow these steps:**

### **Prerequisites** ⚠️ CRITICAL
- **Python 3.12** (NOT 3.11 or earlier - the SDK will not work!)
- **Studio 5000 Logix Designer v35 or later** installed on your machine
- **Windows Operating System** (Studio 5000 SDK is Windows-only)

### **Installation Steps**

1. **Verify Python 3.12**:
   ```bash
   python --version
   # Must show Python 3.12.x - if not, install Python 3.12 from python.org
   ```

2. **Clone and run setup**:
   ```bash
   git clone https://github.com/ProJewks/THE_Studio5000_AI_Assistant_V35.git
   cd THE_Studio5000_AI_Assistant_V35
   python setup.py
   ```
   This installs dependencies, the SDK wheel, and generates your config in one step —
   see the [TL;DR](#-tldr---one-command-setup) above. Steps 2-3 below are the manual,
   step-by-step equivalent if you'd rather do it yourself.

3. **Install Studio 5000 SDK** (for .ACD files) — only needed if you skip `setup.py`:
   ```bash
   pip install "C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python\logix_designer_sdk-*-py3-none-any.whl"
   ```

4. **Test the Installation**:
   ```bash
   python src/mcp_server/studio5000_mcp_server.py --test
   ```
   ✅ Should show: Documentation indexed, SDK available, tests passing

5. **Ready to Use!** - The server will auto-detect your Studio 5000 installation paths

**Having Issues?** See the [Troubleshooting](#troubleshooting) section below.

## 🚀 AI-Powered Features

### **🧠 Natural Language to PLC Code**
- **AI Code Generation**: Convert plain English to working ladder logic
  - *"Start the motor when the start button is pressed and stop it when the stop button is pressed"* → Complete ladder logic with proper start/stop interlocking
- **Smart Pattern Recognition**: Automatically detects start/stop, timer, counter, and basic I/O patterns
- **Intelligent Tag Creation**: Automatically generates appropriate I/O tags with descriptive names
- **Instruction Validation**: Validates generated code against official Studio 5000 documentation database

### **📁 L5X Project Generation**
- **Project Structure Creation**: Generates L5X project files with programs, routines, and tags (can create routines to be imported into existing projects and can create empty l5x files to be manually developed)
- **Multiple Controller Support**: Support for various Allen-Bradley controllers (1756-L83E, 1756-L85E, etc.)
- **⚠️ Current Limitation**: Generated L5X files may have RLL formatting issues requiring manual fixes
- **Structured Output**: XML structure follows Studio 5000 schema but may need validation
- **💡 Best Practice**: Use for project templates, then add logic manually in Studio 5000

### **🏭 Real .ACD Project Creation**
- **Official Studio 5000 SDK Integration**: Creates genuine .ACD files using Rockwell's official SDK
- **Direct Studio 5000 Compatibility**: .ACD files open directly in Studio 5000 without conversion
- **✅ Empty Project Creation**: Clean ACD templates ready for manual development (RELIABLE)
- **⚠️ Complete Project Creation**: Experimental - SDK partial import for MainProgram/MainTask (UNRELIABLE)
- **Version Control**: Supports different Studio 5000 major revisions (v35 default)
- **💡 Recommended**: Use empty ACD creation + manual L5X import workflow

### **🔍 Vector-Powered Semantic Search**
- **Intelligent L5X Analysis**: Semantic search through massive L5X files (tested with 49k+ lines)
- **Production-Scale Processing**: Handles complex industrial automation projects 
- **Smart Code Insertion**: AI finds optimal positions for new logic in existing routines
- **Dependency Analysis**: Automatic detection of component relationships and dependencies
- **Pattern Recognition**: Understands conveyor control, encoder logic, fault handling, and timer patterns
- **FAISS Vector Database**: Lightning-fast semantic search with embedding-based similarity

### **📐 Technical Drawing Analysis**
- **PDF Engineering Drawings**: Extract and search through technical drawings (P&IDs, electrical schematics, control logic diagrams)
- **AutoCAD Integration**: Parse CAD-generated PDFs with rich text and vector graphics content
- **Equipment Context**: Automatically find drawings referenced by equipment tags and system components
- **Vision AI Enhancement**: Advanced analysis of complex technical diagrams and equipment connections
- **Cross-Reference Capability**: Link drawings with existing L5X code and tag databases for complete system understanding

### **📊 Advanced L5X Analysis System**
- **Real Production Testing**: Verified with actual 2.9MB L5X files from industrial systems
- **Complexity Scoring**: Automatic assessment of routine complexity and refactoring needs
- **Component Mapping**: Tracks timers, counters, tags, and their interconnections
- **Surgical Modifications**: Precise rung insertion without disrupting existing logic
- **Professional Workflow**: Read-only analysis with SDK-powered modification capabilities

### **📚 Documentation Access**
- **Comprehensive Instruction Database**: Searches through official Studio 5000 documentation
- **Smart Search**: Find PLC instructions by name, description, category, or functionality
- **Detailed Information**: Get comprehensive details about instruction syntax, parameters, and usage
- **Category Browsing**: Browse instructions by functional categories (Alarm, Math, Motion, Timer, etc.)
- **Language Support**: Information about which programming languages support each instruction (Ladder, ST, FBD)
- **Real-time Validation**: Instant validation using official Rockwell documentation

## 📋 Detailed Installation Guide

### Prerequisites - READ THIS FIRST! ⚠️

**🚨 CRITICAL REQUIREMENT: Python 3.12 ONLY**
- This project **REQUIRES Python 3.12** - earlier versions will fail
- Studio 5000 SDK is **incompatible** with Python 3.11 and earlier
- **Verify your Python version FIRST** before proceeding

**System Requirements:**
- **Python 3.12.x** (Download from [python.org](https://www.python.org/downloads/))
- **Studio 5000 Logix Designer v35 or later** installed
- **Windows Operating System** (Studio 5000 SDK is Windows-only)
- **Administrator privileges** may be required for initial setup

### Step-by-Step Setup

#### Step 1: Install Python 3.12
1. **Download**: Go to [python.org](https://www.python.org/downloads/) and download Python 3.12
2. **Install**: During installation, **CHECK "Add Python to PATH"** ✅
3. **Verify**: Open Command Prompt and run:
   ```bash
   python --version
   # Must show: Python 3.12.x (if not, restart command prompt)
   ```

#### Step 2: Get the Project
1. **Clone the repository**:
   ```bash
   git clone https://github.com/ProJewks/THE_Studio5000_AI_Assistant_V35.git
   cd THE_Studio5000_AI_Assistant_V35
   ```
2. **Prefer the one-command path?** Run `python setup.py` now and skip to
   [Step 4](#step-4-test-your-installation-) — it does Steps 3 and 3.5 for you, including
   picking your Studio 5000 version. The manual steps below are for anyone who wants full
   control over each piece.

#### Step 3: Install Dependencies (CRITICAL!)
1. **Install all required packages**:
   ```bash
   pip install -r requirements.txt
   ```
   **This installs**: 
   - **Core Components**: BeautifulSoup, XML processing, async support
   - **AI & Vector Search**: PyTorch, sentence-transformers, FAISS vector database
   - **Semantic Analysis**: Vector embeddings for instruction and L5X search
   - **Performance**: Optimized versions for production use
   
   **If you get errors**, try:
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
   
   **Note**: Vector database components (torch, sentence-transformers, faiss-cpu) are included for semantic search capabilities. These enable advanced L5X analysis and instruction search features.

#### Step 3.5: Install Studio 5000 SDK (CRITICAL for .ACD files!) 🚨
**⚠️ TEAMMATES MUST DO THIS STEP** - Skip only if you don't need .ACD file creation

1. **Find the SDK wheel file** in your Studio 5000 installation:
   ```bash
   # Look for this file (version may vary):
   dir "C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python\logix_designer_sdk-*-py3-none-any.whl"
   ```

2. **Install the SDK wheel file**:
   ```bash
   # Replace with your actual file path and version:
   pip install "C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python\logix_designer_sdk-2.0.1-py3-none-any.whl"
   ```

3. **Alternative - if you can't find the wheel file**:
   ```bash
   # Navigate to the SDK directory and install from there:
   cd "C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python"
   pip install logix_designer_sdk-*-py3-none-any.whl
   ```

**Without this step**: Documentation and L5X generation will work, but .ACD file creation will fail!

#### Step 4: Test Your Installation ✅
1. **Run the test command**:
   ```bash
   python src/mcp_server/studio5000_mcp_server.py --test
   ```

2. **You should see**:
   - ✅ "Documentation indexed successfully" (500+ instructions found)
   - ✅ "SDK Available: True" (if you installed the SDK wheel file correctly)
   - ✅ "SDK Available: False" (OK if you skipped SDK installation - L5X generation still works)
   - ✅ Sample search results and code generation tests

3. **If SDK Available shows False** but you installed the wheel file:
   - Check the wheel file path was correct
   - Try: `python -c "import logix_designer_sdk; print('SDK OK')"`

4. **If tests fail completely**, check the [Troubleshooting](#troubleshooting) section

🎉 **You're Ready to Use the Tool!** 🎉

The server will automatically detect your Studio 5000 installation paths. Skip to the [Configuration for Claude Desktop](#configuration-for-claude-desktop) section to start using it!

---

#### Step 5: Configure Environment Variables (Advanced Users Only)
**⚠️ SKIP THIS STEP** - Only needed if Studio 5000 is installed in non-standard locations

   **Option A: Set via Windows Environment Variables**
   - Open System Properties → Environment Variables
   - Add these User or System variables:
     ```
     STUDIO5000_DOC_PATH=C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000
     STUDIO5000_SDK_PATH=C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python
     PYTHON312_PATH=C:\Users\YourUsername\AppData\Local\Programs\Python\Python312\python.exe
     ```

   **Option B: Create `.env` file** (in project root):
   
   ```bash
   STUDIO5000_DOC_PATH=C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000
   STUDIO5000_SDK_PATH=C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python
   PYTHON312_PATH=C:\Users\YourUsername\AppData\Local\Programs\Python\Python312\python.exe
   ```

4. **Find Your Studio 5000 Paths**:
   
   **Documentation Path**: Look for this file in your Studio 5000 installation:
   ```
   <Studio5000_Install>\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000\17691.htm
   ```
   Common locations:
   - `C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000`
   - `C:\Program Files\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000`

   **SDK Path**: Look for the SDK Python folder:
   ```
   C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python
   ```

5. **Test the Server**:
   ```bash
   # Test with environment variables (recommended)
   python src/mcp_server/studio5000_mcp_server.py --test
   
   # Or test with explicit path
   python src/mcp_server/studio5000_mcp_server.py --doc-root "C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000" --test
   ```

   **Successful output should show**:
   - Documentation indexing (hundreds of instructions found)
   - Sample search results
   - AI code generation test
   - SDK availability status

## Configuration for Claude Desktop

**If you ran `python setup.py`**, this is already done — it wrote your real, correct paths
(whatever folder you cloned into, whatever Windows username you're on) into
`claude_desktop_config.snippet.json`, or merged them straight into Claude Desktop's config if
you passed `--write-claude-desktop`. Nothing below to fill in by hand.

**Doing it manually?** Add the following to your Claude Desktop configuration file (typically
found at `%APPDATA%\Claude\config.json`). Replace `YourUsername` and the folder name with
wherever you actually cloned this repo — the folder is only called
`THE_Studio5000_AI_Assistant_V35` if you cloned it with the default name:

### Windows Configuration

**Option A: Using Environment Variables (Recommended)**
```json
{
  "mcpServers": {
    "studio5000-ai-assistant": {
      "command": "python",
      "args": [
        "C:\\Users\\YourUsername\\THE_Studio5000_AI_Assistant_V35\\src\\mcp_server\\studio5000_mcp_server.py"
      ],
      "cwd": "C:\\Users\\YourUsername\\THE_Studio5000_AI_Assistant_V35",
      "env": {
        "STUDIO5000_DOC_PATH": "C:\\Program Files (x86)\\Rockwell Software\\Studio 5000\\Logix Designer\\ENU\\v35\\Bin\\Help\\ENU\\rs5000",
        "STUDIO5000_SDK_PATH": "C:\\Users\\Public\\Documents\\Studio 5000\\Logix Designer SDK\\python"
      }
    }
  }
}
```

**Option B: Using Command Line Arguments**
```json
{
  "mcpServers": {
    "studio5000-ai-assistant": {
      "command": "python",
      "args": [
        "C:\\Users\\YourUsername\\THE_Studio5000_AI_Assistant_V35\\src\\mcp_server\\studio5000_mcp_server.py",
        "--doc-root",
        "C:\\Program Files (x86)\\Rockwell Software\\Studio 5000\\Logix Designer\\ENU\\v35\\Bin\\Help\\ENU\\rs5000"
      ],
      "cwd": "C:\\Users\\YourUsername\\THE_Studio5000_AI_Assistant_V35"
    }
  }
}
```

**Important Notes:**
- Replace `YourUsername` with your actual Windows username
- Adjust the Studio 5000 paths to match your installation
- Use **Python 3.12** - specify full path if needed: `"command": "C:\\Users\\YourUsername\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"`

### Alternative: Using Cursor IDE

If you're using Cursor IDE, the MCP server is available by default when working in this project workspace. The server will automatically use environment variables if set, or you can configure it manually in Cursor's MCP settings. Highly recommend using Cursor IDE for this project. and setting it up with cursor mcp settings (mcp.json)

## 🛠️ Available AI Tools

Once configured, these powerful tools will be available in your AI conversations:

### 🧠 **AI Code Generation Tools**

#### 1. Generate Ladder Logic
**Tool**: `generate_ladder_logic`
**Parameters**: 
- `specification` (string): Natural language description of desired PLC behavior

**Capabilities**:
- **Pattern Recognition**: Automatically detects start/stop, timer, counter, and basic I/O patterns
- **Smart Tag Generation**: Creates appropriate tag names and data types
- **Instruction Validation**: Uses Studio 5000 documentation database for validation

**Example**: *"Create logic to start a motor with a start button and stop it with a stop button"*

#### 2. Create L5X Project  
**Tool**: `create_l5x_project`
**Parameters**:
- `project_spec` (object): Project specification including:
  - `name` (string): Project name
  - `controller_type` (string): Controller model (e.g., "1756-L83E")
  - `specification` (string): Natural language description of logic
  - `save_path` (optional string): File path to save L5X file

**Output**: Complete Studio 5000 L5X project file ready for import

#### 3. Create Empty .ACD Template ✅  
**Tool**: `create_acd_project`  
**Parameters**:
- `project_spec` (object): ACD project specification including:
  - `name` (string): Project name
  - `controller_type` (string): Controller model
  - `major_revision` (integer): Studio 5000 version (default 36)
  - `save_path` (string): File path for .ACD file

**Output**: Empty .ACD file using official Studio 5000 SDK - ready for manual development

**⚠️ Important**: Only creates EMPTY projects. Claims about "complete projects with MainProgram/MainTask" are unreliable.

**💡 Recommended Workflow**: Create empty ACD → Develop logic manually in Studio 5000


#### 4. Validate Ladder Logic ⚡ **Fast & Reliable Validation**
**Tool**: `validate_ladder_logic`
**Parameters**:
- `logic_spec` (object): Contains:
  - `ladder_logic` (string): Ladder logic code to validate
  - `instructions_used` (array): List of PLC instructions used

**🎯 Fast Validation System**:

**Production-Ready Fast Validation** ⚡
- **Speed**: 0.001-0.020 seconds
- **Reliability**: 100% reliable, no external dependencies  
- **Detects**: Syntax errors, invalid instructions, unbalanced parentheses, structure issues, logic patterns
- **Requirements**: None - always works
- **Coverage**: Validates against 500+ Studio 5000 instructions

**Output**: Comprehensive validation report with errors, warnings, and suggestions

**💡 Why Fast Validation is Better**: Instant results, 100% reliability, catches all critical PLC programming errors, and integrates seamlessly with your development workflow. No complex setup required!

### 📚 **Documentation Tools**

#### 5. Search Instructions
**Tool**: `search_instructions`
**Parameters**: 
- `query` (string): Search term (instruction name, description, functionality)
- `category` (optional string): Filter by instruction category

**Features**: Searches through official Studio 5000 documentation database

#### 6. Get Instruction Details
**Tool**: `get_instruction`
**Parameters**:
- `name` (string): Exact instruction name (e.g., "TON", "MOV", "ADD", "PID")

**Output**: Complete instruction information including syntax, parameters, examples, and supported languages

#### 7. List Categories  
**Tool**: `list_categories`
**Parameters**: None (dummy parameter required)

**Output**: All available instruction categories (Alarm, Math, Motion, Timer, etc.)

#### 8. List Instructions by Category
**Tool**: `list_instructions_by_category`
**Parameters**:
- `category` (string): Category name

**Output**: All instructions within the specified category

#### 9. Get Instruction Syntax
**Tool**: `get_instruction_syntax`
**Parameters**:
- `name` (string): Instruction name

**Output**: Detailed syntax and parameter information for the instruction

### 🔍 **L5X Analysis & Vector Search Tools**

#### 10. Search L5X Content
**Tool**: `search_l5x_content`
**Parameters**:
- `query` (string): Natural language search query (e.g., "encoder pulse counter", "jam detection logic")
- `project_file` (string): Path to L5X file to search
- `max_results` (integer): Maximum number of results to return (default: 5)

**Features**: Semantic search through existing L5X files to find relevant logic patterns

#### 11. Analyze L5X Project Structure
**Tool**: `analyze_routine_structure`
**Parameters**:
- `project_file` (string): Path to L5X file to analyze
- `routine_name` (optional string): Specific routine to analyze

**Output**: Complexity analysis, dependency mapping, and refactoring recommendations

#### 12. Find Optimal Insertion Point
**Tool**: `find_insertion_point`
**Parameters**:
- `project_file` (string): Target L5X file
- `new_logic_description` (string): Description of logic to insert
- `routine_name` (string): Target routine for insertion

**Output**: Recommended rung position with confidence score for optimal code placement

#### 13. Smart Logic Insertion
**Tool**: `smart_insert_logic`
**Parameters**:
- `project_file` (string): Target L5X file
- `routine_name` (string): Target routine
- `logic_specification` (string): Natural language description of new logic
- `insertion_point` (integer): Rung position for insertion

**Features**: AI-generated logic insertion at optimal positions with existing code analysis

### 📚 **SDK Documentation Search Tools**

#### 14. Search SDK Documentation
**Tool**: `search_sdk_documentation`
**Parameters**:
- `query` (string): Natural language query about SDK operations
- `limit` (integer): Maximum results to return (default: 10)

**Features**: Search through Studio 5000 SDK documentation with semantic understanding

#### 15. Get SDK Operation Details
**Tool**: `get_sdk_operation_info`
**Parameters**:
- `name` (string): SDK operation name
- `operation_type` (optional string): Filter by type (method, class, enum, example)

**Output**: Detailed SDK operation information with examples and parameters

### 📐 **PDF Technical Drawing Tools**

#### 16. Index PDF Drawings
**Tool**: `index_pdf_drawings`
**Parameters**:
- `pdf_file_path` (string): Path to technical drawings PDF file
- `force_rebuild` (boolean): Force re-indexing of existing cache
- `use_vision_ai` (boolean): Enable advanced vision AI analysis

**Features**: Process and index technical PDF drawings for semantic search

#### 17. Search Technical Drawings
**Tool**: `search_drawings`
**Parameters**:
- `query` (string): Natural language search query (e.g., "motor M001 electrical connections")
- `drawing_type_filter` (optional string): Filter by type (electrical, pid, logic, io_list)
- `equipment_filter` (optional string): Filter by equipment tag

**Output**: Ranked search results with drawing context and page references

#### 18. Find Equipment Context
**Tool**: `find_equipment_context`
**Parameters**:
- `equipment_tag` (string): Equipment identifier (e.g., "M001", "CV-001")
- `context_type` (optional string): Type of context needed (electrical, process, safety)

**Features**: Find all drawings and documentation related to specific equipment

## 🎯 **Three Powerful Approaches for PLC Project Creation**

Your MCP server supports **THREE different approaches** for PLC project creation, each optimized for different use cases:

### **🥇 Approach 1: L5X Generation + Manual Import (WITH LIMITATIONS)**
🎯 **Generates**: L5X project structure with MainProgram and MainTask  
⚠️ **Output**: L5X file that may need manual RLL formatting fixes  
🎯 **Best for**: Project templates and basic structure creation  
🎯 **Manual Steps**: 
   1. Generate L5X template (30 seconds)
   2. Fix RLL formatting issues in text editor
   3. Import corrected L5X into Studio 5000

**Usage**: *"Create an L5X project template for conveyor control"*  
**Tool**: `create_l5x_project`

**⚡ Reality Check:**
- ⚠️ Generated L5X may have XML formatting issues
- ✅ Good for project structure templates
- ✅ Import only the corrected logic you need  
- ✅ Professional workflow once files are validated

### **🥈 Approach 2: Empty .ACD Templates (RELIABLE)**  
✅ **Generates**: Empty .ACD project file (clean template)  
✅ **Output**: Blank project that opens directly in Studio 5000  
✅ **Best for**: Starting point for completely manual development  
🛠️ **Manual Steps**: Create MainProgram and MainTask yourself, develop logic manually  

**Usage**: *"Create an empty .ACD template for manual development"*  
**Tool**: `create_acd_project`

**Why This Works:**
- ✅ 100% reliable empty project creation
- ✅ No complex SDK operations that can fail  
- ✅ Clean foundation for manual development

### **🥉 Approach 3: AI Logic Generation Only (For Existing Projects)**  
🧠 **Generates**: Professional ladder logic with validation  
🧠 **Output**: Copy-paste ready ladder logic code  
🧠 **Best for**: Adding logic to existing company projects  
🧠 **Manual Steps**: Copy generated logic into your existing routines  

**Usage**: *"Generate conveyor control logic for my existing project"*  
**Tool**: `generate_ladder_logic`

### **🎯 Current Status & Recommended Workflow**

**What Actually Works**: ✅ **AI Logic Generation + Empty ACD Templates + Manual Development**

**Realistic Industrial Workflow**:
1. **Generate AI Logic**: *"Create conveyor control with jam detection"* → Professional ladder logic code
2. **Create Empty ACD**: Clean project template ready for development  
3. **Manual Development**: Copy logic into Studio 5000, create MainProgram/MainTask manually
4. **Production Ready**: Fully functional logic developed using AI as assistance

**Why This is Honest and Practical**:
- ✅ **100% reliable empty ACD creation** - No complex failures
- ✅ **AI-generated logic works** - Good foundation for manual development  
- ✅ **Professional workflow** - AI assists, human engineer validates and implements
- ✅ **Zero import issues** - No broken XML or SDK complications

**Reality Check on Advanced Features**:
- ⚠️ **L5X Generation**: Creates structure but may need XML fixes before import
- ⚠️ **Complete ACD Projects**: Experimental SDK features that often fail
- ✅ **Fast Validation**: 100% reliable for catching logic errors
- ✅ **Vector Search**: Works great for analyzing existing projects

## 💡 Usage Examples

Once the MCP server is configured, you can ask questions and generate code like:

### **🧠 AI Code Generation Examples**
- *"Create ladder logic to start a motor when a start button is pressed and stop it when a stop button is pressed"*
- *"Generate a conveyor control system with start, stop, and emergency stop"*
- *"Create a 5-second delay timer for a solenoid valve"*
- *"Build ladder logic for a pump control with auto/manual modes and run hours counter"*
- *"Design a three-station assembly line with interlocking and safety circuits"*

### **📁 Project Creation Examples** 
- *"Create a complete .ACD project with conveyor control logic and safety interlocks"* → **Complete .ACD with MainProgram + logic**
- *"Generate a motor control .ACD project for a 1756-L83E controller"* → **Ready-to-use .ACD file**
- *"Create a complete Studio 5000 L5X project for motor control with start/stop functionality"* → **L5X for import**
- *"Build a complete L5X project for a 3-station assembly line with safety interlocks"* → **Complex L5X projects**
- *"Create an empty .ACD template for manual development"* → **Clean template files**

### **📚 Documentation Examples**
- *"What timer instructions are available in Studio 5000?"*
- *"Show me the complete syntax and parameters for the PID instruction"*
- *"What are all the Motion Control instructions available?"*
- *"How do I use the GSV (Get System Value) instruction in ladder logic?"*
- *"What's the difference between TON, TOF, and RTO timer instructions?"*

### **🔍 Validation Examples**
- *"Validate this ladder logic: XIC(START)XIO(STOP)OTE(MOTOR)"*
- *"Check if my TON timer instruction usage is correct with these parameters"*
- *"Verify that my counter logic follows Studio 5000 best practices"*

### **🔍 L5X Analysis & Vector Search Examples**
- *"Search my existing conveyor project for encoder pulse counting logic"*
- *"Find all timer-based fault detection patterns in my L5X file"* 
- *"Analyze the complexity of my sorter tracking routine"*
- *"Where should I insert jam detection logic in my existing conveyor routine?"*
- *"Find all VFD speed control logic in my production L5X files"*
- *"Show me the dependency map for my encoder feedback system"*

### **📚 SDK Documentation Search Examples**
- *"How do I use the LogixProject.partial_import_rungs_from_xml_file method?"*
- *"What are all the available SDK methods for tag manipulation?"*
- *"Show me examples of using the Studio 5000 SDK for project creation"*
- *"Find SDK operations related to routine analysis and modification"*

### **📐 Technical Drawing Analysis Examples**
- *"Index the technical drawings PDF for my Amazon conveyor system project"*
- *"Find all electrical connections for motor M001 in the drawings"*
- *"Show me the P&ID diagrams related to conveyor CV-001"*
- *"What safety interlocks are shown for the divert gates in the drawings?"*
- *"Find the control logic diagrams for the sorter tracking system"*
- *"Search drawings for jam detection sensor wiring and connections"*

### **🏭 Real-World Applications**
- *"Generate ladder logic for a car wash system with 5 sequential steps"*
- *"Create a complete project for a packaging line with conveyor controls and product counting"*
- *"Build a temperature control system with PID loop and alarm handling"*

The AI will automatically use the MCP server tools to provide accurate, up-to-date information based on your actual Studio 5000 documentation and generate working PLC code.

## 🔄 **Manual Import Workflow (Recommended)**

### **Step-by-Step: From Natural Language to Working PLC Code**

**Scenario**: You need conveyor control logic with jam detection

#### **Step 1: Generate L5X Project**
Ask your AI assistant:
> *"Create a complete L5X project for conveyor control with jam detection using upstream and downstream photoeyes"*

**Result**: Complete L5X file with:
- ✅ MainProgram and MainTask
- ✅ Professional ladder logic  
- ✅ All necessary tags with descriptions
- ✅ Validated instructions

#### **Step 2: Import into Studio 5000**
1. **Open Studio 5000** with your existing project (or create new one)
2. **Go to**: File → Import
3. **Select**: Your generated L5X file  
4. **Choose**: Import MainProgram (or specific components)
5. **Click**: Import
6. **Done!** - Working logic ready to test

#### **Step 3: Customize and Test**
- Map your I/O addresses to the generated tags
- Test the logic in your specific application
- Modify as needed for your requirements

### **🏭 For Company Projects**
- **Use your existing company ACD templates**
- **Generate only the logic you need**  
- **Import into established project structure**
- **Maintain your coding standards and practices**

### **⚡ Pro Tips**
- **Generate multiple L5X files** for different sections (safety, process, I/O)
- **Import selectively** - choose only Programs, only Tags, or only specific Routines
- **Version control friendly** - L5X files work great with Git
- **Team collaboration** - Share generated L5X files with team members

## Troubleshooting

### ❗ Critical Issues

#### 1. **Python Version Mismatch**
**Problem**: MCP server starts but SDK features don't work or you get import errors.

**Solution**:
```bash
# Check your Python version
python --version
# Must show 3.12.x

# If not 3.12, install Python 3.12 and use full path in Claude config:
"command": "C:\\Users\\YourUsername\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"
```

**Why**: Studio 5000 SDK requires Python 3.12 specifically. Earlier versions will cause SDK import failures.

#### 2. **Documentation Path Not Found**
**Problem**: "Main index file not found" or "No instructions found"

**Solution - Find Your Documentation Path**:
1. **Open File Explorer** and search for: `17691.htm`
2. **Look in these common locations**:
   ```
   C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000\17691.htm
   C:\Program Files\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000\17691.htm
   C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v37\Bin\Help\ENU\rs5000\17691.htm
   ```
3. **Set the correct path** (everything except the filename):
   ```bash
   # Via environment variable
   set STUDIO5000_DOC_PATH=C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000
   
   # Or via command line
   python src/mcp_server/studio5000_mcp_server.py --doc-root "C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000" --test
   ```

#### 3. **SDK Not Available**
**Problem**: "Studio 5000 SDK not available" or "SDK import failed"

**Most Common Cause**: **You didn't install the SDK wheel file!** ⚠️

**Solution**:
1. **🚨 CRITICAL: Install the SDK wheel file first**:
   ```bash
   # Find and install the wheel file (most teammates miss this step!)
   pip install "C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python\logix_designer_sdk-*-py3-none-any.whl"
   ```

2. **Check SDK Installation**:
   - Look for: `C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python\`
   - If missing, reinstall Studio 5000 with SDK components

3. **Verify SDK Works**:
   ```bash
   # Test if SDK is now available
   python -c "import logix_designer_sdk; print('SDK OK')"
   ```

4. **If still failing, set SDK Path**:
   ```bash
   set STUDIO5000_SDK_PATH=C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python
   ```

### ⚠️ Common Setup Issues

#### 4. **Server Fails to Start**
**Symptoms**: Server crashes immediately or shows JSON-RPC errors.

**Solutions**:
- **Check Python path in Claude config** - use full path to Python 3.12
- **Verify working directory** - `"cwd"` should point to project root
- **Check file permissions** - ensure read access to all project files
- **Test in isolation**:
  ```bash
  python src/mcp_server/studio5000_mcp_server.py --test
  ```

#### 5. **Environment Variables Not Working**
**Problem**: Server still uses hardcoded paths despite setting environment variables.

**Solutions**:
1. **Restart Command Prompt/IDE** after setting environment variables
2. **Check variable names** (case sensitive):
   - `STUDIO5000_DOC_PATH`
   - `STUDIO5000_SDK_PATH` 
   - `PYTHON312_PATH`
3. **Test environment variables**:
   ```bash
   echo %STUDIO5000_DOC_PATH%
   echo %STUDIO5000_SDK_PATH%
   ```

#### 6. **Claude Desktop Configuration Issues**
**Problem**: MCP server not appearing in Claude Desktop.

**Solutions**:
1. **Check config.json syntax** - use JSON validator
2. **Restart Claude Desktop** completely after config changes
3. **Use absolute paths** - no relative paths in Claude config
4. **Check Claude logs** in `%APPDATA%\Claude\logs\`

### 🔧 **Advanced Troubleshooting**

#### **Fast Validation: 100% Reliable, Zero Setup**

**✅ Current Status: Fast Validation System**

The system now uses **production-ready fast validation** that provides instant, reliable results:

**Why Fast Validation is Superior:**
- ✅ **Instant Results**: 0.001-0.020 seconds validation time
- ✅ **100% Reliability**: No external dependencies or service requirements
- ✅ **Comprehensive Coverage**: Validates against 500+ Studio 5000 instructions
- ✅ **Zero Setup**: Works immediately on any system
- ✅ **Production Ready**: Catches all critical PLC programming errors

**Validation Coverage:**
- ✅ **Syntax Validation**: Balanced parentheses, proper instruction format
- ✅ **Instruction Validation**: Against official Studio 5000 instruction set
- ✅ **Structure Validation**: Logic patterns and best practices
- ✅ **Error Reporting**: Detailed error messages with line numbers
- ✅ **Warning System**: Identifies potential issues and improvements

**No More Complex Setup Required!**

The system has evolved beyond SDK validation dependencies. Fast validation provides all the error detection needed for professional PLC development without any of the setup complexity, service dependencies, or reliability issues.

### 🔧 Advanced Troubleshooting

#### 7. **Multiple Python Versions**
If you have multiple Python versions installed:
```bash
# Use specific Python 3.12 executable
C:\Users\YourUsername\AppData\Local\Programs\Python\Python312\python.exe src/mcp_server/studio5000_mcp_server.py --test

# Or create virtual environment with Python 3.12
py -3.12 -m venv studio5000_env
studio5000_env\Scripts\activate
pip install -r requirements.txt
```

#### 8. **Corporate/Network Restrictions**
**Problem**: Cannot access documentation files due to permissions.

**Solutions**:
- **Run as Administrator** when testing
- **Check antivirus exclusions** for Python and Studio 5000 directories  
- **Verify network drive access** if Studio 5000 is on network share

#### 9. **Studio 5000 Version Compatibility**
**Problem**: Different Studio 5000 version than v35.

**Solutions**:
- **Update documentation path** to match your version (v37, v38, etc.)
- **Update major_revision parameter** in .ACD project creation
- **Check SDK version compatibility**

### 🧪 Testing Commands

Verify your setup with these commands:
```bash
# Test 1: Python version
python --version

# Test 2: Basic server test
python src/mcp_server/studio5000_mcp_server.py --test

# Test 3: Documentation path
dir "C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000\17691.htm"

# Test 4: SDK availability (after installing wheel file)
python -c "import logix_designer_sdk; print('SDK Available')"

# Test 5: Environment variables
echo %STUDIO5000_DOC_PATH%
echo %STUDIO5000_SDK_PATH%
```

### 📞 Getting Help

If you're still having issues:
1. **Run the test command** and capture the full output
2. **Check your Python version** and Studio 5000 installation paths  
3. **Verify all file paths exist** before reporting issues
4. **Include your exact configuration** when asking for help

### Testing the Server

For testing instructions, see **Step 4** in the [installation guide](#step-by-step-setup) above.

## Technical Details

### Architecture
The MCP server consists of four main components:

1. **Documentation Parser** (`studio5000_mcp_server.py`):
   - Parses HTML documentation files using BeautifulSoup
   - Builds an in-memory index of all instructions
   - Extracts instruction names, categories, descriptions, syntax, and parameters
   - Provides fast search and retrieval capabilities

2. **AI Code Assistant** (`ai_assistant/code_assistant.py`):
   - Natural language parsing with pattern recognition
   - Ladder logic generation for start/stop, timer, counter patterns
   - Smart tag creation with appropriate data types
   - Code validation using documentation database

3. **L5X Generator** (`code_generator/l5x_generator.py`):
   - XML-based L5X project file generation
   - Complete project structure with programs, routines, and tags
   - Studio 5000 schema compliance
   - Pretty-printed XML output

4. **Studio 5000 SDK Interface** (`sdk_interface/studio5000_sdk.py`):
   - Real .ACD project creation using official Rockwell SDK
   - Python 3.12 requirement for SDK compatibility
   - Empty project template generation
   - Direct Studio 5000 integration

### MCP Protocol
- Follows the Model Context Protocol specification for AI integration
- JSON-RPC 2.0 communication via stdin/stdout
- Tool-based architecture with 15+ available tools
- Vector-powered semantic search capabilities
- Production-scale L5X file analysis
- Async support for all operations

## 📁 Project Structure

```
THE_Studio5000_AI_Assistant_V35/        # (folder name is whatever you clone it as)
├── setup.py                             # One-command installer — run this first
├── src/                                # Main source code
│   ├── mcp_server/
│   │   └── studio5000_mcp_server.py    # Main MCP server with AI features
│   ├── code_generator/
│   │   ├── l5x_generator.py            # L5X project file generation
│   │   └── templates/                  # L5X XML templates
│   ├── ai_assistant/                   # Enhanced AI assistance
│   │   ├── code_assistant.py           # AI-powered natural language processing
│   │   ├── enhanced_main_assistant.py  # Production-ready AI assistant
│   │   ├── mcp_integration.py          # MCP protocol integration
│   │   └── warehouse_automation_patterns.py # Industrial automation patterns
│   ├── sdk_interface/
│   │   └── studio5000_sdk.py           # Real Studio 5000 SDK integration
│   ├── documentation/                  # Vector-powered documentation search
│   │   ├── instruction_vector_db.py    # Instruction search vector database
│   │   └── instruction_mcp_integration.py # MCP tools for instruction search
│   ├── l5x_analyzer/                   # Advanced L5X file analysis
│   │   ├── l5x_vector_db.py           # L5X semantic search system
│   │   ├── l5x_mcp_integration.py     # L5X analysis MCP tools
│   │   └── sdk_powered_analyzer.py    # SDK-enhanced L5X analysis
│   ├── sdk_documentation/              # SDK documentation search
│   │   ├── sdk_vector_db.py           # SDK documentation vector search
│   │   ├── sdk_doc_parser.py          # SDK documentation parser
│   │   └── mcp_sdk_integration.py     # SDK documentation MCP tools
│   ├── tag_analyzer/                   # Tag analysis and management
│   │   ├── tag_vector_db.py           # Tag-based vector search
│   │   ├── csv_tag_parser.py          # CSV tag file parsing
│   │   └── tag_mcp_integration.py     # Tag analysis MCP tools
│   └── verification/                   # Code validation system
│       ├── sdk_verifier_clean.py      # Fast validation (production)
│       └── sdk_verifier.py           # Legacy SDK validation (deprecated)
├── *_vector_cache/                     # Vector database cache directories
│   ├── instruction_vector_cache/       # Instruction search cache
│   ├── l5x_vector_cache/              # L5X analysis cache
│   ├── sdk_vector_cache/              # SDK documentation cache
│   └── tag_vector_cache/              # Tag analysis cache
├── examples/                           # Example generated projects
├── docs/                              # Additional documentation
├── requirements.txt                    # Python dependencies (includes vector DB)
├── mcp_config.json                    # Sample MCP configuration for Claude
└── README.md                          # This comprehensive documentation
```

### Key Files
- **Main Server**: `src/mcp_server/studio5000_mcp_server.py` (main MCP server with 15+ tools)
- **AI Assistant**: `src/ai_assistant/enhanced_main_assistant.py` (production-ready AI assistant)
- **L5X Generator**: `src/code_generator/l5x_generator.py` (creates importable L5X files)
- **L5X Analyzer**: `src/l5x_analyzer/l5x_vector_db.py` (semantic search through L5X files)
- **Fast Validation**: `src/verification/sdk_verifier_clean.py` (production validation system)
- **SDK Interface**: `src/sdk_interface/studio5000_sdk.py` (creates real .ACD files)
- **Vector Databases**: `*_vector_cache/` directories (FAISS-powered semantic search)
- **Configuration**: Environment variables or command line arguments

## Contributing


### Current Capabilities - HONEST ASSESSMENT

**✅ What Actually Works (Production Ready)**:
- ✅ **Official Studio 5000 documentation parsing** (HTML with vector search)
- ✅ **AI-powered ladder logic text generation** (good foundation for manual development)
- ✅ **Empty .ACD file creation** (reliable SDK-based template generation)
- ✅ **Fast validation system** (0.001s response, 100% reliable)
- ✅ **Vector-powered semantic search** (FAISS-based, production-scale)
- ✅ **L5X file analysis** (tested with 49k+ line files)
- ✅ **SDK documentation search** (comprehensive method database)
- ✅ **Pattern recognition** (start/stop, timer, counter patterns)

**⚠️ What's Partially Working (Needs Manual Fixes)**:
- ⚠️ **L5X project file generation** (creates structure but RLL formatting issues)
- ⚠️ **Complete ACD creation** (experimental SDK partial import features)
- ⚠️ **Smart code insertion** (analysis works, insertion is SDK-dependent)

**🔧 What Needs Development**:
- 🔧 **Proper RLL XML generation** (currently outputs raw text in CDATA)
- 🔧 **Reliable SDK partial import** (complex and error-prone)
- 🔧 **End-to-end project automation** (currently requires manual steps)

### Future Enhancement Opportunities

#### **High Priority (Completed! ✅):**
- ✅ **Complete SDK Integration**: COMPLETED! Full program/task creation now implemented
- ✅ **Routine Import/Export**: COMPLETED! Using SDK's partial import functionality 
- ✅ **Program Structure Creation**: COMPLETED! Automatically creates MainProgram and MainTask
- **Tag Management**: Implement SDK tag creation and management operations (TODO)
- **Advanced Project Operations**: Build, upgrade, and deployment automation (TODO)

#### **Medium Priority (Feature Expansion):**
- **Additional Language Support**: Structured Text (ST) and Function Block Diagram (FBD) generation
- **Enhanced Pattern Recognition**: More complex industrial automation patterns  
- ✅ **SDK Documentation Improvement**: COMPLETED! Parser now finds 63 LogixProject methods + 39 examples = 102+ operations (was 22)
- **Advanced Validation**: Static analysis and best practices checking

#### **Lower Priority (Extended Integration):**
- **Multiple Studio 5000 Versions**: Dynamic version detection and compatibility
- **Integration Extensions**: Support for FactoryTalk View, RSLinx, and other Rockwell tools
- **Cloud Deployment**: Web-based interface for team collaboration
- **Caching System**: Improved performance for large documentation sets

#### **🎯 The Honest Value: AI-Assisted Development Workflow**
The system provides valuable AI assistance for PLC development:
- ✅ **AI Logic Generation**: Convert natural language to ladder logic text (**WORKS WELL**)
- ✅ **Empty ACD Templates**: Clean project files ready for manual development (**RELIABLE**)
- ⚠️ **L5X Structure Creation**: Creates project templates that may need formatting fixes (**PARTIAL**)
- ✅ **Fast Validation**: Instant syntax and instruction checking (**PRODUCTION READY**)
- ✅ **Vector Search**: Analyze existing projects semantically (**PRODUCTION READY**)

**You CAN ask**: *"Generate conveyor control logic with jam detection"* and get high-quality ladder logic code to use as a foundation for manual development. **The AI assists, but human engineers still need to implement and validate the final solution.**

### Development Setup
1. Fork the repository
2. Install Python 3.12 and dependencies
3. Set up environment variables for your Studio 5000 installation
4. Run tests to verify functionality
5. Submit pull requests with clear documentation

## License and Legal

**Important Legal Information**:
- This project is provided as-is for educational and development purposes
- **Studio 5000**, **Logix Designer**, **ControlLogix**, and **Allen-Bradley** are trademarks of **Rockwell Automation, Inc.**
- This software is not affiliated with, endorsed, or supported by Rockwell Automation
- Users must have valid Studio 5000 licenses to use the SDK features
- Generated code and projects should be validated by qualified personnel before use in production environments

**Disclaimer**: This tool assists with PLC programming but does not replace proper engineering practices, safety analysis, or compliance verification required for industrial automation systems.
