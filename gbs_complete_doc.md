# GBS Build Tool (Depanneur) - Complete Line-by-Line Documentation

## Table of Contents
1. [Introduction](#introduction)
2. [Script Header and Environment Setup](#script-header-and-environment-setup)
3. [Module Imports](#module-imports)
4. [Global Variable Declarations](#global-variable-declarations)
5. [Helper Functions](#helper-functions)
6. [Command-Line Argument Parsing](#command-line-argument-parsing)
7. [Configuration and Path Setup](#configuration-and-path-setup)
8. [Package Discovery Functions](#package-discovery-functions)
9. [Source Preparation Functions](#source-preparation-functions)
10. [Repository Metadata Functions](#repository-metadata-functions)
11. [Dependency Resolution Functions](#dependency-resolution-functions)
12. [Build Execution Functions](#build-execution-functions)
13. [Report Generation Functions](#report-generation-functions)
14. [Main Execution Flow](#main-execution-flow)

---

## Introduction

**Purpose:** Depanneur is a package build tool for building RPM packages from git repositories. It handles dependency resolution, parallel building, and generates detailed build reports.

**Example Command:**
```bash
gbs build -A x86_64 --threads 8 --clean-once
```

**What This Does:**
- Build RPM packages for x86_64 architecture
- Use 8 parallel build threads
- Clean build root only once (first build in each thread)

---

## Script Header and Environment Setup

### Lines 1-2: Perl Interpreter Declaration
```perl
#!/usr/bin/perl
#
```
**Purpose:** 
- `#!/usr/bin/perl`: Shebang line tells system to use Perl interpreter
- `#`: Empty comment line (common style separator)

**Execution:** When you run `gbs build`, it eventually calls this Perl script

---

### Lines 3-4: Strict Mode
```perl
use strict;
use warnings;
```
**Purpose:**
- `use strict`: Enforces variable declarations, prevents typos, makes code safer
- `use warnings`: Enables warning messages for potential problems

**Effect:** You must declare variables with `my`, preventing common errors

---

### Lines 5-9: Core Module Imports
```perl
use File::Spec::Functions;
use JSON;
use HTML::Template;
use Time::HiRes qw ( sleep time );
use Digest::MD5 ();
```
**Each Module's Purpose:**
- `File::Spec::Functions`: Cross-platform file path operations (canonpath, catfile, etc.)
- `JSON`: Encode/decode JSON for build reports
- `HTML::Template`: Template engine for generating HTML build reports
- `Time::HiRes`: High-resolution time functions (sub-second sleep)
- `Digest::MD5`: MD5 hash functions (currently unused in this code)

---

### Lines 11-20: BEGIN Block - Library Path Setup
```perl
# Pretreatment for adding build path to search
BEGIN {
  my ($wd) = $0 =~ m-(.*)/- ;
  $wd ||= '.';
  unshift @INC,  "$wd/build";
  unshift @INC,  "$wd";
  $ENV{VIRTUAL_ENV} = "/" if ! defined $ENV{VIRTUAL_ENV};
  unshift @INC,  canonpath("$ENV{VIRTUAL_ENV}/usr/lib/build");
}
```
**Line-by-Line Explanation:**

**Line 12: `BEGIN {`**
- Special Perl block that runs BEFORE any other code
- Even before `use` statements
- Used for critical initialization

**Line 13: `my ($wd) = $0 =~ m-(.*)/- ;`**
- `$0`: Special variable containing script path (e.g., `/usr/bin/depanneur`)
- `=~ m-(.*)/-`: Regular expression to extract directory part
  - `m-...-`: Match operator with `-` as delimiter (instead of `/`)
  - `(.*)`: Capture everything before the last `/`
  - Example: `/usr/bin/depanneur` → captures `/usr/bin`
- `my ($wd)`: Store captured directory in `$wd` variable

**Line 14: `$wd ||= '.';`**
- `||=`: "or-equals" operator (assign if undefined/false)
- If `$wd` is empty (script run from current dir), set it to `'.'`
- Ensures `$wd` always has a value

**Line 15: `unshift @INC, "$wd/build";`**
- `@INC`: Perl's module search path array
- `unshift`: Add to BEGINNING of array (highest priority)
- Adds `<script_dir>/build` to module search path
- Example: If script is in `/usr/bin`, adds `/usr/bin/build`

**Line 16: `unshift @INC, "$wd";`**
- Adds script's own directory to search path
- Allows loading modules in same directory

**Line 17: `$ENV{VIRTUAL_ENV} = "/" if ! defined $ENV{VIRTUAL_ENV};`**
- `%ENV`: Hash containing environment variables
- Checks if `VIRTUAL_ENV` is defined
- If not, sets it to root `/`
- Used for virtual environment support

**Line 18: `unshift @INC, canonpath("$ENV{VIRTUAL_ENV}/usr/lib/build");`**
- `canonpath()`: Cleans up path (removes `..`, extra `/`, etc.)
- Adds `<VIRTUAL_ENV>/usr/lib/build` to search path
- Default: `/usr/lib/build` (since VIRTUAL_ENV defaults to `/`)

**Why This Matters:**
- Ensures build scripts can be found regardless of installation location
- Supports both system-wide and virtual environment installations

---

### Lines 22-36: Additional Module Imports
```perl
use YAML qw(LoadFile);
use threads;
use threads::shared;
use Thread::Queue;
use File::Find ();
use Term::ANSIColor qw(:constants);
use File::Path;
use File::Basename;
use File::Path qw(mkpath rmtree);
use File::Temp qw/ tempfile tempdir /;
use URI;
use POSIX ":sys_wait_h";
use File::Glob ':glob';
use User::pwent qw(getpw);
use POSIX qw(sysconf);
```
**Module Purposes:**
- `YAML`: Read YAML configuration files
- `threads`: Multi-threaded building support
- `threads::shared`: Share variables between threads
- `Thread::Queue`: Thread-safe queue (imported but unused)
- `File::Find`: Recursively find files in directories
- `Term::ANSIColor`: Colored terminal output (GREEN, RED, YELLOW)
- `File::Path`: Create/remove directory trees
- `File::Basename`: Extract filename/directory from paths
- `File::Temp`: Create temporary files/directories
- `URI`: Parse and manipulate URLs for repositories
- `POSIX`: System constants and functions
- `File::Glob`: File globbing with bsd_glob
- `User::pwent`: Get user information

---

### Lines 37-38: Build-Specific Modules
```perl
use Config::Tiny;
use Parallel::ForkManager;
```
**Module Purposes:**
- `Config::Tiny`: Parse INI-style `.gbs.conf` files
- `Parallel::ForkManager`: Fork processes for parallel source export

---

### Lines 41-42: Comment Header
```perl
# Global vars
```
Simple section marker for global variable declarations

---

## Global Variable Declarations

### Lines 44-51: Thread Synchronization Variables
```perl
# Flag to inform all threads that application is terminating
my $TERM:shared=0;

# Prevents double thread workers detach attempts
my $DETACHING:shared;

# Flag to inform main thread update pkgdeps
my $dirty:shared=0;

my %export_packs:shared = ();
my $export_lock:shared;
```

**Line 45: `my $TERM:shared=0;`**
- `:shared`: Special attribute making variable accessible to all threads
- `$TERM`: Termination flag (0 = keep running, 1 = stop all threads)
- Used when user presses Ctrl+C or build completes

**Line 48: `my $DETACHING:shared;`**
- Lock variable to prevent race conditions
- Used with `lock($DETACHING)` to protect critical sections
- Ensures only one thread modifies shared data at a time

**Line 51: `my $dirty:shared=0;`**
- "Dirty" flag indicating repository metadata needs refresh
- Set to 1 when a package finishes building
- Main loop checks this and updates dependencies

**Lines 53-54: Export tracking (currently unused)**
- `%export_packs:shared`: Hash for tracking exported packages
- `$export_lock:shared`: Lock for export operations

---

### Lines 55-59: File::Find Variables
```perl
# Set the variable $File::Find::dont_use_nlink if you're using AFS,
# since AFS cheats.

# For the convenience of &wanted calls, including -eval statements:
use vars qw/*name *dir *prune/;
```

**Line 55-56:** Comment about AFS filesystem (Andrew File System)

**Line 59: `use vars qw/*name *dir *prune/;`**
- Declares global variables for File::Find callbacks
- `*name`: Typeglob for `$File::Find::name` (full path to current file)
- `*dir`: Typeglob for `$File::Find::dir` (current directory)
- `*prune`: Typeglob for `$File::Find::prune` (stop descending)

**Lines 60-62: Alias declarations**
```perl
*name   = *File::Find::name;
*dir    = *File::Find::dir;
*prune  = *File::Find::prune;
```
- Creates shortcuts: `$name` instead of `$File::Find::name`
- Used in `wanted` callback functions (like `git_wanted`)

---

### Lines 64-71: User Identity
```perl
my ($zuid, $zgid);
# Get UID/GID for source code manipulates
if (getlogin()) {
     ($zuid, $zgid) = (getpwnam(getlogin()))[2,3];
} else {
     ($zuid, $zgid) = (getpwuid($<))[2,3];
}
```

**Line 64:** Declare variables for user ID and group ID

**Line 66: `if (getlogin()) {`**
- `getlogin()`: Returns login name of user
- Returns empty string if not available (e.g., in cron)

**Line 67: `($zuid, $zgid) = (getpwnam(getlogin()))[2,3];`**
- `getpwnam()`: Get password entry by username
- Returns array: (name, passwd, uid, gid, quota, comment, gcos, dir, shell)
- `[2,3]`: Extract elements 2 and 3 (uid and gid)
- Stores numeric user ID and group ID

**Lines 68-70: Fallback method**
- `$<`: Special variable containing real UID
- `getpwuid()`: Get password entry by UID
- Same extraction of uid and gid

**Purpose:** 
- Used with `--uid` option when calling build script
- Ensures build runs with correct user permissions
- Prevents permission issues in build root

---

### Lines 74-88: More Module Imports
```perl
use Cwd qw(cwd abs_path);
use Getopt::Long;
use Pod::Usage;
use File::Temp qw/ tempfile tempdir /;
use Build;
use Build::Rpm;
use Build::Rpmmd;
use BSSolv;
use Data::Dumper;
use File::Basename;
```

**Critical Build Modules:**
- `Build`: Core OBS build script functionality
- `Build::Rpm`: RPM spec file parser
- `Build::Rpmmd`: Repository metadata parser
- `BSSolv`: Build Service dependency solver
- `Data::Dumper`: Debug output for complex data structures

---

### Lines 90-91: Constants
```perl
# "sudo -v" period
use constant SUDOV_PERIOD => 3*60;
```
- Defines how often to refresh sudo credentials
- 180 seconds (3 minutes)
- Prevents sudo timeout during long builds

**Line 92:**
```perl
use constant SC_NPROCESSORS_ONLN => 84;
```
- POSIX constant for querying number of CPU cores
- Used to determine parallel job count

---

### Lines 93-124: Build Configuration Variables
```perl
my @threads;                    # TODO: clean up
my @exclude = ();               # exclude build packages list
my @repos= ();                  # rpm repositoies list
my $arch = "i586";              # build arch, default is i586
my $path = "";                  # build path, which contails packages git content
my $style = "git";              # code style, git (default) or osc
my $clean = 0;                  # clean build root for building if $clean == 1
my $binarylist = "";            # packages binay list to be built
my $binary_from_file = "";      # file contains binary rpms to be built
my $commit = "HEAD";            # store the commit_ID used to be built
my $spec_commit = "";           # store the commit_ID used for get spec files
my $includeall = 0;             # build all content of including uncommitted and untracked files
```

**Detailed Variable Explanations:**

**Line 93: `my @threads;`**
- Array to hold thread objects (note: marked TODO, may be deprecated)
- Currently not actively used

**Line 94: `my @exclude = ();`**
- Array of package names to exclude from build
- Populated from `--exclude` options or exclude file
- Example: `@exclude = ('package1', 'package2')`

**Line 95: `my @repos = ();`**
- Array of repository URLs
- Can be local paths or HTTP URLs
- Example: `('http://repo.tizen.org/base/', '/local/repo')`

**Line 96: `my $arch = "i586";`**
- Default target architecture
- Overridden by `-A` or `--arch` option
- Valid values: i586, x86_64, armv7l, aarch64, etc.

**Line 97: `my $path = "";`**
- Path to directory containing package source code
- If empty, defaults to `$build_root/packages`
- Set via `--path` option

**Line 98: `my $style = "git";`**
- Source code management style
- Options: 'git' (default), 'obs', 'tar'
- Determines how packages are discovered and exported

**Line 99: `my $clean = 0;`**
- Boolean flag for `--clean` option
- 1 = clean build root before every build
- 0 = reuse existing build root

**Line 100: `my $binarylist = "";`**
- Comma-separated list of binary package names to build
- Set via `--binary-list` option
- Example: `"package1,package2,package3"`

**Line 101: `my $binary_from_file = "";`**
- Path to file containing list of binaries to build
- Set via `--binary-from-file` option
- File format: one package name per line

**Line 102: `my $commit = "HEAD";`**
- Git commit/branch/tag to build from
- Default "HEAD" means current commit
- Set via `--commit` option
- Example: `"v1.2.3"` or `"abc123def"`

**Line 103: `my $spec_commit = "";`**
- Separate commit for spec files only
- Allows building old source with new spec
- Set via `--spec-commit` option

**Line 104: `my $includeall = 0;`**
- Boolean flag for `--include-all` option
- 1 = include uncommitted and untracked files
- 0 = only use committed files
- Useful for testing local changes

---

### Lines 105-119: More Configuration Variables
```perl
my $upstream_branch = "";       # upstream branch name
my $upstream_tag = "";          # upstream tag name used for generate tar ball
my $fallback_to_native = 0;    # fallback to native packaging mode if export fails
my $squash_patches_until = "";  # Commit_ID used for generate one patch
my $no_patch_export = 0;        # don't generate patches if it's 1
my $packaging_dir = "packaging";# packaging dir
my $dist = "tizen";             # distribution name
my $rdeps_build = 0;            # build all packages depend on specified packages
my $deps_build = 0;             # build all packages specified packaged depend on
my $dryrun = 0;                 # just show build order and don't build actually
my $help = 0;                   # show help information
my $keepgoing = "on";           # If a package build fails, do not abort and continue
my $fail_fast = 0;              # stop build immediately if one of packages fails
my $clean_repos = 0;            # clean corresponding local rpm repos
my $create_baselibs = 0;        # create baselibs packages if baselibs.conf exists
```

**Key Variables Explained:**

**Line 105-106: Upstream source control**
- `$upstream_branch`: Git branch containing pristine upstream source
- `$upstream_tag`: Git tag for upstream version
- Used by `gbs export` to generate source tarballs

**Line 107: `$fallback_to_native = 0;`**
- If tarball generation fails, try native packaging
- Native = no separate upstream tarball, just package directory

**Line 108: `$squash_patches_until = "";`**
- Create one patch from all commits up to this point
- Reduces number of patch files

**Line 110: `$packaging_dir = "packaging";`**
- Subdirectory in git repo containing RPM packaging files
- Contains: .spec file, patches, additional sources
- Can be overridden per-package in `.gbs.conf`

**Line 111: `$dist = "tizen";`**
- Distribution name (tizen, fedora, opensuse, etc.)
- Determines which `.conf` build config to use
- Affects package dependencies and build macros

**Line 112-113: Dependency build modes**
- `$rdeps_build`: Reverse dependencies (packages that depend on target)
- `$deps_build`: Forward dependencies (packages target depends on)
- Both can be enabled with `--rdeps` and `--deps`

**Line 114: `$dryrun = 0;`**
- When 1, show build order but don't actually build
- Useful for testing dependency resolution

**Line 116: `$keepgoing = "on";`**
- "on" = continue building other packages if one fails
- "off" = stop immediately on first failure
- Different from `$fail_fast`

**Line 117: `$fail_fast = 0;`**
- When 1, abort entire build on first failure
- Takes precedence over `$keepgoing`

---

### Lines 120-126: Path Variables
```perl
my $skip_srcrpm = 0;            # don't generate source rpm package if $skip_srcrpm == 1

my $virtualenv = "$ENV{'VIRTUAL_ENV'}";    # virtual env dir, default is '/'
my $build_root = $ENV{TIZEN_BUILD_ROOT};   # depanneur output dir
$build_root = expand_filename($build_root);# expand ~/, ~<user> etc.
my $localrepo = "$build_root/local/repos"; # generated local repo dir
my $order_dir = "$build_root/local/order"; # intermediate repo data file
```

**Line 123: `my $virtualenv = "$ENV{'VIRTUAL_ENV'}";`**
- Gets virtual environment path from environment
- Default is `/` (set in BEGIN block)

**Line 124: `my $build_root = $ENV{TIZEN_BUILD_ROOT};`**
- Main build directory, set by GBS before calling depanneur
- Example: `/home/user/GBS-ROOT`
- All build artifacts go here

**Line 125: `$build_root = expand_filename($build_root);`**
- Expands `~` to home directory
- Example: `~/GBS-ROOT` → `/home/user/GBS-ROOT`

**Line 126: `my $localrepo = "$build_root/local/repos";`**
- Where built RPMs are stored
- Structure: `$localrepo/$dist/$arch/RPMS/`

**Line 127: `my $order_dir = "$build_root/local/order";`**
- Stores `.repo.cache` files
- Contains parsed repository metadata

---

### Lines 128-144: More Path Variables
```perl
my $depends_dir = "$build_root/local/depends"; # package's reverse dependency dir
my $cache_dir = "$build_root/local/cache"; # cache binary rpms downloaded from remote repos
my $groupfile="$build_root/meta/group.xml";# group information for yum
my $patternfile="$build_root/meta/patterns.xml"; # group information for zypp
my $build_dir = canonpath("$virtualenv/usr/lib/build"); # build script directory
$ENV{'BUILD_DIR'} = $build_dir; # must change env variable in main thread
my $config_filename = "$build_root/meta/local.yaml";
my $dist_configs = "$build_root/meta/dist"; # dist confs dir
my $exclude_from_file = "$build_root/meta/exclude"; # default exclude file
my $cleanonce = 0;      # only clean the same build root for the first time
my $debug = 0;          # enable debug feature
my $incremental = 0;    # do incremental build
my $run_configure = 0;  # run %configure in spec files
my $overwrite = 0;      # rebuilt packages if it's already built out
my $MAX_THREADS = 1;    # max threads depanneur creates
my $extra_packs = "";   # extra packages which should install to build root
my $ccache = 0;         # use ccache to speed up building
```

**Critical Paths:**

**Line 131: `my $build_dir = ...`**
- Path to OBS build scripts
- Contains: `build`, `createrepomddeps`, `createdirdeps`, etc.
- Default: `/usr/lib/build`

**Line 132: `$ENV{'BUILD_DIR'} = $build_dir;`**
- Sets environment variable for child processes
- Build scripts use this to find their dependencies

**Line 133: `my $config_filename = "$build_root/meta/local.yaml";`**
- GBS configuration file
- Contains repository URLs, credentials, etc.

**Line 134: `my $dist_configs = "$build_root/meta/dist";`**
- Directory containing build configuration files
- Example files: `tizen.conf`, `fedora.conf`
- Defines package dependencies and build settings

**Line 138: `my $incremental = 0;`**
- When 1, mount source directory directly in build root
- Allows editing source during build
- Useful for debugging build failures

**Line 141: `my $MAX_THREADS = 1;`**
- Number of parallel build threads
- Set by `--threads` option
- Example: `--threads 8` → builds 8 packages simultaneously

---

### Lines 145-165: Advanced Configuration Variables
```perl
my $pkg_ccache = "";    # use ccacahge /path/to/ccache.tar
my $icecream = 0;       # use icecream to specify the number of parallel processes
my $noinit = 0;         # don't check build root, just go into it and building
my $keep_packs = 0;     # don't remove useless rpm packages from build root
my $thread_export = 0;  # use thread when gbs export source code
my $use_higher_deps = 0; # which repo provides higher version deps, use it
my $not_export_source = 0; # do not export source
my @defines;            # define extra macros for 'rpmbuild'
my $arg_spec = "";      # spec file to be built this time
my $start_time = "";    # build start time
my $gbs_version = "";   # show gbs version info in final report
```

**Important Variables:**

**Line 149: `my $noinit = 0;`**
- When 1, skip build root initialization
- Assumes build root already configured
- Faster for repeated builds

**Line 151: `my $thread_export = 0;`**
- Experimental threaded export (deprecated)
- Now uses Parallel::ForkManager instead

**Line 153: `my $not_export_source = 0;`**
- When 1, skip source export for some packages
- Reads list from `/usr/share/depanneur/not-export`
- Optimization for packages that don't need export

**Line 154: `my @defines;`**
- Array of RPM macro definitions
- Example: `["_with_ssl 1", "_without_doc 1"]`
- Passed to rpmbuild with `--define`

---

### Lines 167-184: Package Management Data Structures
```perl
my @tofind = ();        # for resolve final build binary list
my @pre_packs = ();       # temp packages data, item structure :
                          #           {project_base_path:
                          #            filepath: spec file path }
my %to_build = ();      # for all packages should be built this time
my %subptomainp = ();   # dict to store map from subpack name to main pack name.
my %repo = ();          # store all packages dependency in memory
my %pkgdeps = ();       # direct and indirect dependency dict
my %pkgddeps = ();      # direct dependency dict
my %pkgrdeps = ();      # expanded reversed dependency dict
my %pkgrddeps = ();     # direct reversed dependency dict
my %source_cache = ();  # package_path:commit_ID = > export_dir
my %rpmpaths = ();      # dict to store map from pkg name to rpm paths in local repo
my %srpmpaths = ();     # dict to store map from pkg name to srpm paths in local repo
my %visit    = ();      # visit dict for resolving circles
```

**Data Structure Explanations:**

**Line 168: `my @pre_packs = ();`**
- Temporary storage during package discovery
- Each element is hash ref:
  ```perl
  {
    filename => "/path/spec1.spec,/path/spec2.spec",
    project_base_path => "/path/to/git/repo",
    packaging_dir => "packaging",
    upstream_branch => "upstream",
    upstream_tag => "v1.0"
  }
  ```

**Line 171: `my %to_build = ();`**
- Final hash of packages to build
- Key: package name
- Value: hash ref with metadata
  ```perl
  {
    name => "mypackage",
    version => "1.0",
    release => "1",
    deps => [...],
    subpacks => [...],
    filename => "/path/to/spec"
  }
  ```

**Line 172: `my %subptomainp = ();`**
- Maps sub-package names to main package
- Example: `{"mypackage-devel" => "mypackage"}`
- Used in dependency resolution

**Line 173: `my %repo = ();`**
- Contains all available packages from repositories
- Structure:
  ```perl
  {
    "package.x86_64" => {
      provides => ["package", "package(x86-64)"],
      requires => ["glibc", "libssl"],
      recommends => ["package-doc"]
    }
  }
  ```

**Line 174-177: Dependency dictionaries**
- `%pkgdeps`: All dependencies (direct + transitive)
  - Example: `{"pkg1" => ["dep1", "dep2", "dep3"]}`
- `%pkgddeps`: Only direct dependencies
  - Example: `{"pkg1" => ["dep1"]}`  
- `%pkgrdeps`: All reverse dependencies (packages depending on this)
  - Example: `{"pkg1" => ["pkg2", "pkg3"]}`
- `%pkgrddeps`: Only direct reverse dependencies

**Line 178: `my %source_cache = ();`**
- Caches exported source locations
- Key: `"repo_path:commit_id"`
- Value: path to exported source
- Example: `{"/path/to/repo:abc123" => "/build/sources/pkg-1.0"}`

**Line 179-180: RPM path mappings**
- Maps package names to file paths
- Used to find and remove old RPM versions
- Example: `{"mypackage.x86_64" => ["/path/to/mypackage-1.0.rpm"]}`

---

### Lines 186-195: Build State Tracking
```perl
my @running :shared = (); # threads shared, store all running workers
my @done :shared = ();    # threads shared, store all packages already build done
my @skipped = ();         # store packages skipped
my  %left_pkg= ();          #store package  caused circle

my @cleaned : shared = ();# affect on --clean-once specified, store cleaned threads
my %errors :shared;       # threads shared, store packages build error
my %succeeded :shared;    # threads shared, store packages build succeeded
my %expansion_errors = ();# dict structure of packages with expansion dependency error
my @export_errors;        # list store packages with export error
my %tmp_expansion_errors = ();
```

**Thread-Shared Arrays:**

**Line 186: `my @running :shared = ();`**
- Package names currently being built
- Updated when thread starts building
- Example: `["package1", "package3", "package5"]`

**Line 187: `my @done :shared = ();`**
- Package names that finished (success or failure)
- Prevents re-building same package

**Line 188: `my @skipped = ();`**
- Packages skipped (SRPM already exists, not overwriting)

**Line 191: `my @cleaned :shared = ();`**
- Thread IDs that already cleaned their build root
- Used with `--clean-once`
- Example: `[0, 3, 5]` means threads 0, 3, 5 cleaned

**Line 192: `my %errors :shared;`**
- Maps failed package name to log file path
- Example: `{"package1" => "/path/to/logs/fail/package1/log.txt"}`

**Line 193: `my %succeeded :shared;`**
- Maps successful package name to log file path
- Example: `{"package2" => "/path/to/logs/success/package2/log.txt"}`

**Line 194: `my %expansion_errors = ();`**
- Packages with dependency resolution errors
- Value is array of missing dependencies
- Example: `{"package3" => ["missing-lib", "another-dep"]}`

---

### Lines 196-210: Build Status and Configuration
```perl
my $packages_built :shared  = 0; # if there's package build succeeded
my %build_status_json = ();      # final json report data
my %workers = ();                # build workers: { 'state' => 'idle'|'busy' , 'tid' => undef|$tid };
my @build_order = ();  #The build order for all packages
my $get_order = 0; #Bool :  @build_order is empty
my $not_export_cf = "/usr/share/depanneur/not-export";
my @not_export = ();
my $vmtype = "";
my $vmmemory = "";
my $vmdisksize = "";
my $vmdiskfilesystem = "";
my $vminitrd = "";
my $vmkernel = "";
my $vmswapsize = "";
my $disable_debuginfo = 0;#disable debuginfo when using build cmd
```

**Key Variables:**

**Line 196: `my $packages_built :shared = 0;`**
- Boolean flag (0 or 1)
- Set to 1 when any package builds successfully
- Determines if repository metadata needs updating

**Line 197: `my %build_status_json = ();`**
- Hash containing final build report data
- Converted to JSON and HTML
- Contains: summary, errors, build details, paths

**Line 198: `my %workers = ();`**
- Thread pool management
- Structure for each worker:
  ```perl
  {
    0 => { state => 'idle', tid => undef },
    1 => { state => 'busy', tid => 12345 },
    ...
  }
  ```
- `state`: 'idle' or 'busy'
- `tid`: Thread ID when busy, undef when idle

**Line 199: `my @build_order = ();`**
- Topologically sorted package list
- Packages with no dependencies come first
- Example: `["base-lib", "mid-lib", "app"]`

**Line 203-211: VM build options**
- KVM virtual machine build support
- `$vmtype = "kvm"`: Enable VM build
- Memory, disk, filesystem, kernel settings
- More isolated than chroot builds

---

### Lines 211-217: More Configuration Variables
```perl
my $depends = 0; #depends subcommand to put reverse dependency
my $depends_local_only = 0; #generate depends xml only from local repos
my $reverse_off = 0; #disable reverse dependency
my $reverse_on = 1; #enable reverse dependency
my $export_only = 0; # only export, not building
my $tarfile = 0; # generate tar file for dependence & reverse dependence xml file
my $preordered_list = ""; # List of ordered packages to support user defined build order calculation
```

**Line 211: `my $depends = 0;`**
- When 1, run in "depends mode"
- Only generate dependency XML, don't build
- Used for analysis

**Line 215: `my $export_only = 0;`**
- When 1, only export source code
- Skip building entirely
- Useful for preparing sources

---

### Lines 218-221: Final Global Variables
```perl
my $profiling = ""; # Reference profiling report location. If set reports will be generated
my $with_submodules = 0; #didn't export sub modules source code.
my $work_done = 0; # Whether build jobs finished
my $release_tag = ""; # Override Release in spec file
my $nocumulate = 0; # Whether build without cumulative build.
```

**Line 220: `my $work_done = 0;`**
- Set to 1 after all builds complete
- Used to recalculate package dependencies from repodata

---

## Command-Line Argument Parsing

### Lines 223-290: GetOptions Block
```perl
GetOptions (
    "repository=s" => \@repos,
    "arch=s" => \$arch,
    "dist=s" => \$dist,
    "configdir=s" => \$dist_configs,
    "clean" => \$clean,
    "clean-once" => \$cleanonce,
    "exclude=s" => \@exclude,
    ...
```

**How GetOptions Works:**
- Parses command-line arguments
- Updates variables directly
- Format: `"option-name=type" => \$variable`

**Option Types:**
- `=s`: String value required
- No suffix: Boolean flag
- Multiple occurrences append to array

**Example Command:**
```bash
gbs build -A x86_64 --threads 8 --clean-once
```

**Variables Set:**
- `$arch = "x86_64"` (from `-A x86_64`)
- `$MAX_THREADS = 8` (from `--threads 8`)
- `$cleanonce = 1` (from `--clean-once`)

---

### Lines 292-402: Help Text
```perl
if ( $help ) {
    print "
Depanneur is a package build tool based on the obs-build script.

Available options:

    --arch <Architecture>
      Build for the specified architecture.
    ...
```

**Purpose:**
- Displays help when `--help` specified
- Documents all available options
- Exits immediately after printing

---

## Helper Functions

### Lines 407-413: debug() Function
```perl
sub debug {
    my $msg = shift;
    $msg =~ s#://[^@]*@#://#g;
    print MAGENTA, "debug: ", RESET, "$msg\n" if $debug == 1;
}
```

**Line-by-Line:**

**Line 408: `my $msg = shift;`**
- Gets first parameter (debug message)

**Line 409: `$msg =~ s#://[^@]*@#://#g;`**
- Regular expression substitution
- Pattern: `://[^@]*@` (URL with credentials)
- Replacement: `://` (removes credentials)
- Example: `http://user:pass@repo.com` → `http://repo.com`
- **Security:** Prevents passwords in logs

**Line 410: `print MAGENTA, "debug: ", RESET, "$msg\n" if $debug == 1;`**
- Only prints if `$debug` flag is 1
- `MAGENTA`: ANSI color code
- `RESET`: Return to normal color
- Output: <span style="color: magenta">debug:</span> message

---

### Lines 417-421: info() Function
```perl
sub info {
    my $msg = shift;
    print GREEN, "info: ", RESET, "$msg\n";
}
```

**Purpose:**
- Print informational message in green
- Always prints (not conditional)
- Example output: <span style="color: green">info:</span> building package

---

### Lines 425-429: warning() Function
```perl
sub warning {
    my $msg = shift;
    print YELLOW, "warning: ", RESET, "$msg\n";
}
```

**Purpose:**
- Print warning message in yellow
- Non-fatal issues
- Example: package skipped, symlink found

---

### Lines 433-437: error() Function
```perl
sub error {
    my $msg = shift;
    print RED, "error: ", RESET, "$msg\n";
    exit 1;
}
```

**Purpose:**
- Print error message in red
- Exits with status 1 (failure)
- **Fatal errors only**

---

### Lines 447-479: my_system() Function
```perl
sub my_system {
    my $cmd = shift;
    debug("my_system: $cmd");
    my $ret;
    my $pid;
    my @out = ();
    
    if (wantarray) {
        defined($pid=open(PIPE, "-|")) or die "Can not fork: $!\n";
    } else {
        defined($pid=fork) or die "Can not fork: $!\n";
    }

    unless ($pid) {  # Child process
        open(STDERR, ">&STDOUT");
        exec ($cmd);
        exit -1;
    } else {  # Parent process
        if (wantarray) {
            while (my $line = <PIPE>) {
                print $line;
                push @out, $line;
            }
        }
        waitpid ($pid,0);
        $ret = $?;
        close(PIPE) if wantarray;

        return wantarray ? ($ret, @out): $ret;
    }
}
```

**How It Works:**

**Line 448-449:** Get command and log it

**Line 453: `if (wantarray)`**
- Checks calling context
- `wantarray`: Returns true if caller expects list
- Different behavior for scalar vs array context

**Array Context (caller wants output):**
```perl
my ($status, @output) = my_system("ls -l");
```

**Scalar Context (caller only wants exit code):**
```perl
my $status = my_system("make install");
```

**Line 454: `defined($pid=open(PIPE, "-|"))`**
- Fork process AND open pipe in one operation
- `-|`: Special open mode for reading from child
- Returns child PID to parent, 0 to child

**Line 456: Fork without pipe**
- Used when output not needed
- Simpler, faster

**Lines 459-462: Child process**
- `unless ($pid)`: True in child (PID is 0)
- `open(STDERR, ">&STDOUT")`: Redirect stderr to stdout
- `exec($cmd)`: Replace process with command
- `exit -1`: Only reached if exec fails

**Lines 463-476: Parent process**
- If pipe opened, read output line by line
- Print each line (real-time output)
- Store in `@out` array
- `waitpid($pid, 0)`: Wait for child to finish
- `$?`: Special variable with exit status
- Return exit code, or exit code + output

---

### Lines 485-498: expand_filename() Function
```perl
sub expand_filename {
    my $path = shift;
    my $home_dir = sub { 
        my $p = getpw($_[0]) or die "$_[0] is not a valid username\n";
        return $p->dir();
    };
    
    $path =~ s{^~(?=/|$)}{ $ENV{HOME} ? "$ENV{HOME}" : $home_dir->( $< ) }e
          or $path =~ s{^~(.+?)(?=/|$)}{ $home_dir->( $1 ) }e;
    return $path;
}
```

**Purpose:** Expand `~` in paths

**Examples:**
- `~/mydir` → `/home/user/mydir`
- `~john/mydir` → `/home/john/mydir`

**Line 487-490: Helper closure**
- Anonymous subroutine to get home directory
- `getpw()`: Get user info by UID or username
- `->dir()`: Extract home directory path

**Line 492-493: Two substitution patterns**

**Pattern 1:** `^~(?=/|$)`
- `^~`: Starts with tilde
- `(?=/|$)`: Followed by slash or end of string
- Matches: `~` or `~/...`
- Replaces with: `$ENV{HOME}` or current user's home

**Pattern 2:** `^~(.+?)(?=/|$)`
- `^~(.+?)`: Tilde followed by username
- `(?=/|$)`: Before slash or end
- Matches: `~username` or `~username/...`
- Replaces with: That user's home directory

**The `e` modifier:** Evaluates replacement as Perl code

---

### Lines 502-532: is_archive_filename() Function
```perl
sub is_archive_filename {
    my $basename = shift;
    my @arhive_formats = ('tar', 'zip');
    my %archive_ext_aliases = ( 
        'tgz' => ['tar', 'gzip' ],
        'tbz2'=> ['tar', 'bzip2'],
        'tlz' => ['tar', 'lzma' ],
        'txz' => ['tar', 'xz'   ]
    );
    my %compressor_opts = ( 
        'gzip'  => [['-n'], 'gz'  ],
        'bzip2' => [[],     'bz2' ],
        'lzma'  => [[],     'lzma'],
        'xz'    => [[],     'xz'  ]
    );

    my @split = split(/\./, $basename);
    if (scalar(@split) > 1) {
        if (exists $archive_ext_aliases{$split[-1]}) {
            return 1;
        } elsif (grep($_ eq $split[-1], @arhive_formats)) {
            return 1;
        } else {
            foreach my $value (values %compressor_opts) {
                if ($value->[1] eq $split[-1] && scalar(@split) > 2 &&
                    grep($_ eq $split[-2], @arhive_formats)){
                    return 1;
                }
            }
        }
    }

    return 0;
}
```

**Purpose:** Check if filename is a source archive

**Recognized Formats:**
- `.tar`, `.zip`
- `.tgz`, `.tbz2`, `.tlz`, `.txz` (aliases)
- `.tar.gz`, `.tar.bz2`, `.tar.xz`, `.tar.lzma`

**Algorithm:**
1. Split filename by `.` 
2. Check last component against known extensions
3. If compound extension, check last two components
4. Return 1 if match, 0 if not

**Used in:** Spec file parsing to identify Source tarballs

---

### Lines 537-547: read_not_export() Function
```perl
sub read_not_export {
    my $file = shift;

    open (CF, "<", $file) or print "Error: open file: $file error!\n $!\n" and return;
    while (<CF>) {
        chomp();
        next if (/^s*#/);
        push @not_export, $_;
    }
    close (CF);
}
```

**Purpose:** Read list of packages that don't need export

**File Format:**
```
# Comment lines start with #
package1
package2
package3
```

**Populates:** `@not_export` array

**Used for:** Optimization - skip export for certain packages

---

### Lines 549-553: Validation Checks
```perl
if ($incremental == 1 && $style ne 'git') {
    error("incremental build only support git style packages");
}
if ($style ne 'git' && $style ne 'obs' && $style ne 'tar') {
    error("style should be 'git' or 'obs'");
}
```

**Purpose:** Validate command-line option combinations

---

## Configuration Loading

### Lines 555-567: Load GBS Configuration
```perl
my @package_repos = ();
my $Config;
if (-e $config_filename) {
    $Config = LoadFile($config_filename);
    if (!$Config) {
        error("Error while parsing $config_filename");
    }
}
```

**Loads:** `~/GBS-ROOT/meta/local.yaml`

**Example YAML Content:**
```yaml
Repositories:
  - Url: http://download.tizen.org/releases/base/latest/repos/
    Username: user
    Password: pass
  - Url: /local/repo
```

---

### Lines 569-583: Extract Repository URLs
```perl
if (@repos) {
    @package_repos = @repos;
} else {
    if ($Config){
        foreach my $r (@{$Config->{Repositories}}) {
            my $uri = URI->new($r->{Url});
            if ( $r->{Password} && $r->{Username} ) {
                $uri->userinfo($r->{Username} . ":" . $r->{Password});
            }
            if ($uri->scheme ne "file") {
                push(@package_repos, $uri);
            }
        }
    }
}
```

**Logic:**
1. If `--repository` specified, use those
2. Otherwise, load from config file
3. Create URI objects with embedded credentials
4. Skip `file://` URLs (local directories)

**Result:** `@package_repos` contains all repository URLs

---

### Lines 585-609: Handle --noinit Mode
```perl
my $scratch_dir = "$build_root/local/BUILD-ROOTS/scratch.$arch";

if ($noinit == 1) {
    my $scratch = "$scratch_dir.0";
    if (! -e "$scratch") {
        error("build root:$scratch does not exist...");
    }

    open(my $file, '<', "$scratch/.guessed_dist") ||
        die "read dist name failed: $!";
    $dist = readline($file);
    close($file);
    chomp $dist;
    
    $dist =~ s!^.*/(.*)\.conf!$1!;
    $dist_configs= "$scratch";
    
    if (! -e "$dist_configs/$dist.conf") {
        error("build root broken...");
    }
}
```

**Purpose of --noinit:**
- Skip build root initialization
- Use existing build root
- Faster for repeated builds

**What It Does:**
1. Check build root exists
2. Read distribution name from `.guessed_dist` file
3. Extract config name (e.g., `tizen` from `tizen.conf`)
4. Set `$dist_configs` to build root location
5. Verify config file exists

---

### Lines 611-618: Set Build Paths
```perl
my $pkg_path = "$build_root/local/sources/$dist";
my $cache_path = "$build_root/local/sources/$dist/cache";
my $success_logs_path = "$localrepo/$dist/$arch/logs/success";
my $fail_logs_path = "$localrepo/$dist/$arch/logs/fail";
my $rpm_repo_path = "$localrepo/$dist/$arch/RPMS";
my $srpm_repo_path = "$localrepo/$dist/$arch/SRPMS";
```

**Directory Structure Created:**
```
~/GBS-ROOT/
├── local/
│   ├── sources/
│   │   └── tizen/
│   │       ├── package-1.0-1/  (exported source)
│   │       └── cache/          (export cache)
│   └── repos/
│       └── tizen/
│           └── x86_64/
│               ├── RPMS/       (binary packages)
│               ├── SRPMS/      (source packages)
│               └── logs/
│                   ├── success/
│                   └── fail/
```

---

### Lines 620-631: mkdir_p() Function
```perl
sub mkdir_p {
    my $path = shift;
    my $err_msg;
    
    my $mkdir_out = File::Path::make_path( $path, { error => \my $err } );
    
    if (@$err) {
        for my $diag (@$err) {
            my ( $file, $message ) = %$diag;
            $err_msg .= $message;
        }
        print STDERR "$err_msg";
    }
}
```

**Purpose:** Create directory and all parent directories

**Similar to:** `mkdir -p` command in shell

**Error Handling:** Collects and prints all errors

---

### Lines 633-645: Create Build Directories
```perl
if ( $exclude_from_file ne "" && -e $exclude_from_file ) {
    debug("using $exclude_from_file for package exclusion");
    open my $file, '<', $exclude_from_file  or die $!;
    @exclude = <$file>;
    chomp(@exclude);
    close($file);
}

mkdir_p("$order_dir");
mkdir_p($success_logs_path);
mkdir_p($fail_logs_path);
mkdir_p($cache_path);
mkdir_p($rpm_repo_path);
if ($skip_srcrpm == 0){
    mkdir_p($srpm_repo_path);
}
```

**Load Exclude File:**
- One package name per line
- Comments allowed with `#`
- Appends to `@exclude` array

**Create Directories:**
- Order directory for cache files
- Log directories for success/fail
- Cache for repository metadata
- RPM output directories

---

### Lines 647-649: Initialize Package Array
```perl
my @packs;
my $package_path = "";
```

**Purpose:**
- `@packs`: Will hold all discovered packages
- `$package_path`: Base directory for package search

---

## Architecture Configuration

### Lines 652-664: Architecture Policy
```perl
my %archpolicies = (
    "x86_64"      =>  ["x86_64", "i686", "i586", "i486", "i386", "noarch"],
    "i586"        =>  ["i686", "i586", "i486", "i386", "noarch"],
    "aarch64"     =>  ["aarch64", "noarch"],
    "armv7hl"     =>  ["armv7hl", "noarch"],
    "armv7l"      =>  ["armv7l", "armv7el", "armv6l", "armv5tejl", "armv5tel", "armv5l", "armv4tl", "armv4l", "armv3l", "noarch"],
    "armv6l"      =>  ["armv6l", "armv5tejl", "armv5tel", "armv5l", "armv4tl", "armv4l", "armv3l", "noarch"],
    "mips"        =>  ["mips", "noarch"],
    "mipsel"      =>  ["mipsel", "noarch"],
    "riscv32"     =>  ["riscv64", "noarch"],
    "riscv64"     =>  ["riscv64", "noarch"],
);
```

**Purpose:** Define compatible architectures

**Example for x86_64:**
- Can use packages built for x86_64, i686, i586, i486, i386, noarch
- Wider architecture first (more specific)
- noarch always compatible (architecture-independent)

**Why This Matters:**
- Repository may have i586 package but no x86_64
- x86_64 build can use the i586 package
- Dependency resolution needs to know what's compatible

---

### Lines 666-670: Validate and Set Architecture
```perl
error("$arch not support") if (not exists $archpolicies{$arch});

my @archs = @{$archpolicies{$arch}};
my $archpath = join(":", @archs);
```

**For `--arch x86_64`:**
- `@archs = ("x86_64", "i686", "i586", "i486", "i386", "noarch")`
- `$archpath = "x86_64:i686:i586:i486:i386:noarch"`

**Used By:** Build config and dependency resolver

---

### Lines 673-675: Load Build Configuration
```perl
my $config = Build::read_config_dist($dist, $archpath, $dist_configs);
push @{$config->{'macros'}}, "%define opensuse_bs 0";
```

**What This Does:**
1. Reads `$dist_configs/tizen.conf` (or other dist)
2. Parses build requirements, macros, package mappings
3. Returns hash reference with configuration

**Config File Contains:**
- Required packages for build environment
- RPM macro definitions
- Package name mappings
- Dependency resolution rules

**Line 674:** Adds macro indicating not building in OBS
- OBS = Open Build Service
- Some spec files have conditional logic for OBS

---

## Package Discovery

### Lines 677-685: Determine Package Path
```perl
if ( -d "$packaging_dir" && -d ".git" ) {
    $package_path = cwd();
} else {
    if ( $path eq "" ) {
        $package_path = "$build_root/packages";
    } else {
        $package_path = abs_path($path);
    }
}
```

**Logic:**
1. If current directory has `packaging/` and `.git/`: use current directory
2. Else if `--path` not specified: use `~/GBS-ROOT/packages`
3. Else: use specified path

**Common Scenarios:**
- Single package build: Run from package directory
- Multi-package build: Point to directory containing multiple packages

---

### Lines 690-699: Package Discovery Functions

#### git_wanted() Callback
```perl
sub git_wanted {
    if( -d "$name/.git" ){
        fill_packs_from_git("$name/.git");
        $prune = 1;
    }
}
```

**Purpose:** File::Find callback for git repositories

**How It Works:**
- Called for each file/directory found
- `$name`: Full path (set by File::Find)
- If directory contains `.git`, process it
- `$prune = 1`: Don't descend into subdirectories
  - Each git repo is independent
  - Prevents finding submodules

**Workflow:**
```
packages/
├── package1/
│   └── .git/        ← Found! Call fill_packs_from_git()
│       └── .git/    ← Don't descend (pruned)
├── package2/
│   └── .git/        ← Found! Call fill_packs_from_git()
└── package3/
    └── .git/        ← Found! Call fill_packs_from_git()
```

---

#### obs_wanted() Callback
```perl
sub obs_wanted {
    /^.*\.spec\z/s && fill_packs_from_obs($name);
}
```

**Purpose:** Find spec files for OBS-style packages

**Pattern:** `/^.*\.spec\z/s`
- `^.*\.spec`: Any characters followed by .spec
- `\z`: End of string (not line)
- `s`: Single-line mode

**Calls:** `fill_packs_from_obs()` with spec file path

---

#### fill_packs_from_obs() Function
```perl
sub fill_packs_from_obs {
    my $name = shift;
    $name =~ m/\.osc/ || push(@packs, $name);
}
```

**Purpose:** Add OBS spec file to package list

**Filter:** Skip files in `.osc` directories (OBS metadata)

---

### Complete fill_packs_from_git() Function

*This function was already documented in detail above. Here's a summary:*

```perl
sub fill_packs_from_git {
    # 1. Extract package directory from .git path
    # 2. Check exclude list
    # 3. Load .gbs.conf overrides if present
    # 4. Find spec files (from git or filesystem)
    # 5. Handle symlinks in packaging directory
    # 6. Add package metadata to @pre_packs
}
```

**Key Points:**
- Supports both committed files (git show) and local files (--include-all)
- Handles symlinked packaging directories
- Reads per-package configuration from .gbs.conf
- Stores multiple spec files as comma-separated string

---

## Source Preparation Phase

This section covers how source code is exported from git repositories to build directories.

### Lines 1145-1149: Check for --export-only
```perl
if ($export_only) {
    info("export done");
    exit 0;
}
```

**Purpose:** Exit after export if `--export-only` specified

---

### Lines 1151-1160: Prepare Source Code (Git Style)
```perl
if ($style eq 'git') {
    File::Find::find({wanted => \&git_wanted}, $package_path );
    foreach my $p (@pre_packs) {
       my $specs = $p->{"filename"};
       my @spec_list = split(",", $specs);
       if (@spec_list > 1 && $commit ne "HEAD"){
           error("--commit option can't be specified with multiple packages");
       }
    }
```

**Line 1152:** Recursively search for git repositories
- Calls `git_wanted()` for each file/directory
- Populates `@pre_packs` array

**Lines 1153-1158:** Validation
- Each package in `@pre_packs` may have multiple spec files
- If multiple specs AND specific commit specified: ERROR
- Why: Can't specify one commit for packages with multiple specs

---

### Lines 1162-1167: Check if Packages Found
```perl
    if (@pre_packs == 0) {
        error("No source package found at $package_path");
    }
    if ($incremental == 0) {
        info("prepare sources...");
        read_not_export($not_export_cf);
```

**Validation:** At least one package must be found

**Line 1166:** Load list of packages that skip export
- File: `/usr/share/depanneur/not-export`
- Performance optimization

---

### Lines 1169-1219: Parallel Source Export

This is one of the most complex sections. Let me break it down:

```perl
        my @data_queue = ();
        foreach my $pack (@pre_packs) {
            if ($not_export_source == 1) {
                my $name = basename($pack->{"project_base_path"});
                my $r = grep /^$name$/, @not_export;
                if ($vmtype eq "kvm") {
                    $r = 0;
                }
                if ($r) {
                    info("skip export $name for accel...");
                    # ... add directly to @packs
                } else {
                    info("package $name not support skip export source");
                    push @data_queue, $pack;
                }
            } else {
                push @data_queue, $pack;
            }
        }
```

**Purpose:** Filter packages that need export

**Logic:**
1. If `$not_export_source` enabled AND package in skip list: add directly to `@packs`
2. Else: add to `@data_queue` for export
3. KVM builds always export (need clean source)

---

### Lines 1197-1204: Setup Fork Manager
```perl
        my $thread_num = int(sysconf(SC_NPROCESSORS_ONLN));
        if ($thread_num > 28) {
            $thread_num = 28;
        }
        my $pm = Parallel::ForkManager->new($thread_num);
        my %export_ret = ();
```

**Line 1197:** Get number of CPU cores
- `sysconf(SC_NPROCESSORS_ONLN)`: POSIX function for online CPUs
- Example: Returns 32 on 32-core machine

**Line 1198-1200:** Limit to 28 processes
- Too many processes can overwhelm system
- Git operations are I/O intensive

**Line 1201:** Create fork manager
- `Parallel::ForkManager`: Manages pool of forked processes
- Limits concurrent processes
- Collects results from children

**Line 1202:** Hash to collect export results
- Key: package filename
- Value: array of exported package data

---

### Lines 1205-1211: Setup Result Callback
```perl
        $pm->run_on_finish (
            sub {
                my ($pid, $exit_code, $ident, $exit_signal, $core_dump, $data_structure_reference) = @_;
                if (defined($data_structure_reference)) {
                    $export_ret{$ident} = $data_structure_reference;
                }
            }
        );
```

**Purpose:** Called when each child process finishes

**Parameters:**
- `$pid`: Child process ID
- `$exit_code`: Exit status
- `$ident`: Identifier (package filename)
- `$data_structure_reference`: Data returned from child

**Action:** Store returned data in `%export_ret`

---

### Lines 1212-1220: Fork and Export
```perl
        foreach my $pack (@data_queue) {
            my $pid = $pm->start($pack->{"filename"}) and next;
            my @packs_arr = ();
            srand();
            @packs_arr = prepare_git($config, $pack->{"project_base_path"}, $pack->{"filename"},
                    $pack->{"packaging_dir"}, $pack->{"upstream_branch"}, $pack->{"upstream_tag"});
            $pm->finish(0, \@packs_arr);
        }
        $pm->wait_all_children;
```

**Line 1213:** Start child process
- `$pm->start()`: Fork new process
- Returns PID in parent, 0 in child
- `and next`: Parent continues loop, child executes below

**Line 1215:** Re-seed random number generator
- Each forked child inherits parent's RNG state
- `srand()`: Randomize again
- Important for unique temporary filenames

**Line 1216-1217:** Call prepare_git()
- Exports source code for this package
- Returns array of exported package data

**Line 1218:** Finish child process
- `$pm->finish(status, data)`: Exit child, return data to parent
- Status 0 = success
- Data passed to `run_on_
**Line 1219:** Wait for all children to complete
- Blocks until all forked processes finish
- Ensures all exports complete before continuing

---

### Lines 1221-1228: Collect Export Results
```perl
        foreach my $key (keys %export_ret) {
            my $arr = $export_ret{$key};
            foreach my $pack (@{$arr}) {
                push @packs, $pack;
            }
        }
```

**Purpose:** Merge results from all child processes

**Data Flow:**
1. Each child returns array of package data
2. Stored in `%export_ret` by callback
3. Now flatten all arrays into single `@packs` array

**Result:** `@packs` contains all successfully exported packages

---

### The prepare_git() Function (Detailed)

```perl
sub prepare_git {
    my $config = shift;
    my $base = shift;
    my $specs = shift;
    my $packaging_dir = shift;
    my $upstream_branch = shift;
    my $upstream_tag = shift;

    my @packs_arr = ();
    my @spec_list = split(",", $specs);
```

**Parameters:**
- `$config`: Build configuration hash
- `$base`: Git repository path
- `$specs`: Comma-separated spec file paths
- `$packaging_dir`: Where packaging files are
- `$upstream_branch`/`$upstream_tag`: For tarball generation

**Line 849:** Split comma-separated spec list into array

---

### Lines 850-906: Process Each Spec File

```perl
    foreach my $spec (@spec_list) {
        my $spec_file = basename($spec);

        if ($includeall == 0 || $spec_commit ne "") {
            my $tmp_dir = abs_path(tempdir(CLEANUP=>1));
            my $tmp_spec = "$tmp_dir/$spec_file";
            my $without_base;
            $spec =~ s!\Q$base/\E!!;
            $without_base = $spec;
            if (my_system("cd '$base'; git show $spec_commit:$without_base >'$tmp_spec' 2>/dev/null") != 0) {
                warning("failed to checkout spec file from commit: $spec_commit:$without_base");
                return;
            }
            $spec = $tmp_spec;
        }
```

**Line 851:** Get just filename from full path

**Lines 853-865: Checkout spec from git if needed**
- Create temporary directory (auto-cleanup)
- Remove base path from spec path
- Use `git show` to extract spec from specific commit
- If fails, return empty (package skipped)
- Update `$spec` to point to temp file

**Purpose:** 
- Normal mode: Get spec from git commit
- --include-all mode: Use spec from filesystem

---

### Lines 868-874: Parse Spec File
```perl
        my $pack = Build::Rpm::parse($config, $spec);
        if (! exists $pack->{name} || ! exists $pack->{version} || ! exists $pack->{release}) {
            debug("failed to parse spec file: $spec, name,version,release fields must be present");
            return;
        }
        my $pkg_name = $pack->{name};
        my $pkg_version = $pack->{version};
        my $pkg_release = $pack->{release};
```

**Line 868:** Parse spec file
- Returns hash with name, version, release, deps, etc.
- Uses RPM macro expansion

**Lines 869-871:** Validation
- Spec must have Name, Version, Release fields
- If missing, skip this package

**Lines 872-874:** Extract key fields
- Will be used to construct cache key

---

### Lines 875-895: Check Export Cache
```perl
        my $cache_key = "$pkg_name-$pkg_version-$pkg_release";
        my $cached_rev = read_cache($cache_key);
        my $skip = 0;
        my $current_rev = '';

        if (! -e "$base/.git") {
            warning("not a git repo: $base/.git!!");
            return;
        } else {
            $current_rev = query_git_commit_rev($base, $commit);
            $skip = ($cached_rev eq $current_rev) && (-e "$pkg_path/$cache_key/$spec_file");
            $source_cache{"$base:$cached_rev"} = "$pkg_path/$cache_key" if ($skip);
        }
```

**Line 875:** Create cache key
- Format: `package-1.0-1`
- Used for cache files and export directory

**Line 876:** Read cache
- Check if we've exported this before
- Cache file contains git commit ID

**Lines 880-889: Determine if can skip export**
- Verify `.git` directory exists
- Get current commit ID
- Skip if: cached commit matches current commit AND export directory exists
- If skipping, store path in `$source_cache`

**Cache File Location:** `~/GBS-ROOT/local/sources/tizen/cache/package-1.0-1`

**Cache File Content:** Git commit ID (e.g., `abc123def456...`)

---

### Lines 898-917: Perform Export or Use Cache
```perl
        if (!$skip || $includeall == 1) {
            my $val = ($includeall == 1) ? "include-all" : $current_rev;
            info("start export source from: $base ...");
            
            if ($includeall != 1 && exists $source_cache{"$base:$current_rev"}) {
                my $exported_key = basename($source_cache{"$base:$current_rev"});
                my_system("cp -r '$pkg_path'/'$exported_key'  '$pkg_path'/'$cache_key'");
                my_system("cp -f '$pkg_path'/cache/'$exported_key' '$pkg_path'/cache/'$cache_key'");

                my $src_rpm = "$srpm_repo_path/$cache_key.src.rpm";
                if (-f "$src_rpm") {
                    my_system("rm -f '$src_rpm'");
                }
            } else {
                unless (write_cache($cache_key, $val, $base, $spec_file, $packaging_dir, $upstream_branch, $upstream_tag)) {
                    clean_cache($cache_key);
                    debug("$pkg_name was not exported correctly");
                    return;
                }
            }
            $source_cache{"$base:$current_rev"} = "$pkg_path/$cache_key";
        }
```

**Scenario 1: Can skip export**
- Do nothing, use cached export

**Scenario 2: Include-all mode**
- Always export (may have uncommitted changes)

**Scenario 3: Already exported from same commit (multi-spec)**
- Copy previous export to new cache key
- Example: `package.spec` and `package-extra.spec` from same repo
- Copy `package-1.0-1/` to `package-extra-1.0-1/`

**Scenario 4: Need fresh export**
- Call `write_cache()` to actually export
- If export fails, clean up and skip package

**Line 917:** Store export path for future multi-spec packages

---

### Lines 920-934: Verify Export and Add to Pack List
```perl
        if ( -e "$pkg_path/$cache_key/$spec_file" ){
            my $pack;
            $pack->{'filename'} = "$pkg_path/$cache_key/$spec_file";
            $pack->{'project_base_path'} = $base;
            push @packs_arr, $pack;
        }else{
            warning("spec file $spec_file has not been exported to $pkg_path/$cache_key/ correctly,".
                    " please check if there're special macros in Name/Version/Release fields");
        }
    }

    return @packs_arr;
}
```

**Lines 920-926:** Verify export succeeded
- Check if spec file exists in export directory
- Create package data structure
- Add to return array

**Lines 927-929:** Export verification failed
- Spec file missing (export failed silently)
- Common cause: RPM macros in Name/Version/Release that can't be expanded

**Line 933:** Return array of exported packages
- Will be collected by Parallel::ForkManager

---

### The write_cache() Function

```perl
sub write_cache {
    my ($cache_key, $cache_val, $base, $spec, $packaging_dir, $upstream_branch, $upstream_tag) = @_;
    my $cache_fname = "$cache_path/$cache_key";
    my @export_out;
    my $out_dir = "$pkg_path/$cache_key";

    @export_out = gbs_export($base, $spec, $packaging_dir, $upstream_branch, $upstream_tag, $out_dir);
    if (shift @export_out) {
        push(@export_errors, {package_name => $cache_key,
                              package_path => $base,
                              error_info   => \@export_out});
        return;
    }

    my $src_rpm = "$srpm_repo_path/$cache_key.src.rpm";
    if (-f "$src_rpm") {
        my_system("rm -f '$src_rpm'");
    }

    open(my $rev1, "+>", "$cache_fname") ||
        die "write reversion cache($cache_fname) failed: $!";
    print $rev1 $cache_val . "\n";
    close($rev1);
    1;
}
```

**Lines 672-677:** Setup
- `$cache_fname`: Where to store commit ID
- `$out_dir`: Where to export source

**Line 679:** Call gbs_export()
- Returns array: (exit_code, @output_lines)
- Exit code 0 = success

**Lines 680-684:** Handle export failure
- Add to `@export_errors` for reporting
- Return without value (undefined = failure)

**Lines 686-689:** Remove old SRPM if exists
- Forces rebuild even if SRPM exists
- Ensures fresh build with new source

**Lines 691-694:** Write cache file
- Store commit ID in cache file
- Used for next build to skip export

**Line 695:** Return success (true value)

---

### The gbs_export() Function

```perl
sub gbs_export {
    my ($base, $spec, $packaging_dir, $upstream_branch, $upstream_tag, $out_dir) = @_;
    my @args = ();
    my $cmd;
    push @args, "gbs";
    push @args, "--debug" if ($debug);
    push @args, "export";
    push @args, "'$base'";
    push @args, "-o '$out_dir'";
    push @args, "--outdir-directly";
    push @args, "--spec $spec";
    if ($includeall == 1) {
        push @args, "--include-all";
    } else {
        push @args, "--commit=$commit";
    }
    if (! $upstream_branch eq "") {
        push @args, "--upstream-branch='$upstream_branch'";
    }
    if (! $upstream_tag eq "") {
        push @args, "--upstream-tag='$upstream_tag'";
    }
    if ($fallback_to_native == 1) {
        push @args, "--fallback-to-native";
    }
    if (! $squash_patches_until eq "") {
        push @args, "--squash-patches-until=$squash_patches_until";
    }
    if (! $packaging_dir eq "") {
        push @args, "--packaging-dir=$packaging_dir";
    }
    if ($no_patch_export == 1) {
        push @args, "--no-patch-export";
    }
    if ($thread_export == 1){
        push @args, " 2>&1 | grep -v warning | grep -v Creating";
    }
    if ($with_submodules == 1) {
       push @args, "--with-submodules";
    }

    $cmd = join(" ", @args);
    return my_system($cmd);
}
```

**Purpose:** Build and execute gbs export command

**Command Structure:**
```bash
gbs export \
  '/path/to/repo' \
  -o '/path/to/output' \
  --outdir-directly \
  --spec mypackage.spec \
  --commit=HEAD \
  --packaging-dir=packaging
```

**Key Options:**
- `--outdir-directly`: Don't create subdirectory for package
- `--include-all`: Export uncommitted changes too
- `--commit`: Specific commit to export
- `--upstream-branch/tag`: For tarball generation
- `--fallback-to-native`: If tarball fails, use native mode
- `--squash-patches-until`: Combine patches into one
- `--no-patch-export`: Don't generate patch files
- `--with-submodules`: Include git submodules

**What gbs export does:**
1. Creates source tarball from upstream branch/tag
2. Generates patch files for all commits since upstream
3. Copies spec file and other packaging files
4. Prepares directory structure for rpmbuild

**Export Directory Structure:**
```
package-1.0-1/
├── package.spec
├── package-1.0.tar.gz         (upstream tarball)
├── 0001-first-patch.patch
├── 0002-second-patch.patch
└── other-source-files
```

---

## Repository Metadata Retrieval

This section handles scanning repositories to build dependency database.

### Lines 1242-1246: Start Metadata Retrieval
```perl
info("retrieving repo metadata...");
my $repos_setup = 1;
my_system("> '$order_dir'/.repo.cache.local");
```

**Line 1243:** Success flag (will be set to 0 if any repo fails)

**Line 1244:** Create empty local cache file
- `>` operator truncates file to zero length
- Ensures clean start

---

### Lines 1247-1251: Scan Local Repository
```perl
if (-d "$rpm_repo_path") {
    my_system("$build_dir/createdirdeps '$rpm_repo_path' >> '$order_dir'/.repo.cache.local");
    my_system("echo D: >> '$order_dir'/.repo.cache.local");
}
```

**Purpose:** Extract metadata from local RPM repository

**createdirdeps:** OBS script that reads RPM headers
- Input: Directory containing RPM files
- Output: Dependency information in repo cache format

**Format (appended to .repo.cache.local):**
```
F:package.arch-buildtime/installtime/0: /path/to/package.rpm
P:package.arch-buildtime/installtime/0: package = 1.0 package(arch) = 1.0
R:package.arch-buildtime/installtime/0: libc.so.6 libssl.so
I:package.arch-buildtime/installtime/0: package-1.0-1 buildtime
D:
```

**Line 1249:** Add delimiter `D:` to separate local from remote repos

---

### Lines 1252-1268: Scan Remote Repositories
```perl
my_system("> '$order_dir'/.repo.cache.remote");
foreach my $repo (@package_repos) {
    my $cmd = "";
    if ($repo =~ /^\// && ! -e "$repo/repodata/repomd.xml") {
        $cmd = "$build_dir/createdirdeps '$repo' >> '$order_dir'/.repo.cache.remote ";
    } else {
        $cmd = "$build_dir/createrepomddeps --cachedir='$cache_dir' '$repo' >> '$order_dir'/.repo.cache.remote ";
    }
    debug($cmd);
    if ( my_system($cmd) == 0 ) {
        my_system("echo D: >> '$order_dir'/.repo.cache.remote");
    } else {
        $repos_setup = 0;
    }
}
```

**Line 1252:** Create empty remote cache file

**Lines 1253-1267: Process each repository**

**Decision Logic:**
1. If path starts with `/` AND no repodata: Local directory, use `createdirdeps`
2. Otherwise: Remote repo or local with repodata, use `createrepomddeps`

**createdirdeps:** 
- Reads RPM headers directly from files
- Used for directories without repo metadata
- Slower but works with plain RPM directories

**createrepomddeps:**
- Downloads and parses repository metadata (XML files)
- Caches downloaded metadata in `$cache_dir`
- Much faster for remote repos
- Used for: HTTP URLs, local repos with repodata

**Lines 1261-1266:** Execute and check result
- Append delimiter after each successful repo
- Set `$repos_setup = 0` if any fails

---

### Lines 1269-1270: Merge Cache Files
```perl
my_system("cat '$order_dir'/.repo.cache.local '$order_dir'/.repo.cache.remote >'$order_dir'/.repo.cache");
```

**Purpose:** Combine local and remote metadata

**Order Matters:**
- Local packages listed first
- Takes precedence in dependency resolution
- Freshly built packages used before remote ones

**Result:** Single `.repo.cache` file with all package metadata

---

### Lines 1272-1274: Check Setup Success
```perl
if ($repos_setup == 0 ) {
    error("repo cache creation failed...");
}
```

**Fatal Error:** Can't proceed without repository metadata

---

## Package Parsing

### Lines 1276-1278: Parse All Packages
```perl
info("parsing package data...");
my %packs = parse_packs($config, @packs);
%to_build = %packs;
```

**Input:** `@packs` array from source export
**Output:** `%to_build` hash with package metadata

---

### The parse_packs() Function

```perl
sub parse_packs {
    my ($config, @packs) = @_;
    my %packs = ();
    my %tmp_sub_to_main = ();
```

**Purpose:** Parse all spec files and extract metadata

**Line 1014:** `%packs`: Return value (all parsed packages)
**Line 1015:** `%tmp_sub_to_main`: Map sub-packages to main package

---

### Lines 1017-1026: Process Each Package
```perl
    foreach my $spec_ref (@packs) {
        my $spec;
        my $base;
        if (ref($spec_ref) eq "HASH") {
            $spec = $spec_ref->{filename};
            $base = $spec_ref->{project_base_path};
        } else {
            $spec = $spec_ref;
        }
```

**Flexibility:** Handles both hash refs and plain strings
- Git style: Hash with filename and base path
- OBS style: Just spec file path

---

### Lines 1027-1036: Parse Spec and Check Architecture
```perl
        my $pack = Build::Rpm::parse($config, $spec);
        
        if ( ( $pack->{'exclarch'} ) &&  ( ! grep $_ eq $archs[0], @{$pack->{'exclarch'}} ) ) {
            warning($pack->{name} . ": build arch not compatible: " . join(" ", @{$pack->{'exclarch'}}));
            next;
        }
        if ( ( $pack->{'badarch'} ) &&  ( grep $_ eq $archs[0], @{$pack->{'badarch'}} ) ) {
            warning($pack->{name} . ": build arch not compatible: " . join(" ", @{$pack->{'badarch'}}));
            next;
        }
```

**Line 1027:** Parse spec file
- Expands RPM macros
- Extracts: name, version, release, dependencies, sub-packages

**Lines 1029-1032:** Check ExclusiveArch
- Spec can specify which architectures are supported
- Example: `ExclusiveArch: x86_64 aarch64`
- Skip if our architecture not in list

**Lines 1033-1036:** Check ExcludeArch  
- Opposite of ExclusiveArch
- Example: `ExcludeArch: i586`
- Skip if our architecture in exclude list

---

### Lines 1037-1042: Extract Package Info
```perl
        my $name = $pack->{name};
        my $version = $pack->{version};
        my $release = $pack->{release};
        my @buildrequires = $pack->{deps};
        my @subpacks = $pack->{subpacks};
        my @sources = ();
```

**Build Dependencies:** `@buildrequires`
- Packages needed to build this package
- Example: `['gcc', 'make', 'autoconf', 'libtool']`

**Sub-packages:** `@subpacks`
- Binary packages produced by this spec
- Example: Main package `mylib` produces:
  - `mylib` (runtime library)
  - `mylib-devel` (headers)
  - `mylib-docs` (documentation)

---

### Lines 1043-1055: Find Source Tarballs
```perl
        for my $src (keys %{$pack}) {
            next if $src !~ /source/;
            next if (is_archive_filename($pack->{$src}) == 0);
            push @sources, $src;
        }
        
        my @sorted =  sort {
            my $l = ($a =~ /source(\d*)/)[0];
            $l = -1 if ($l eq "");
            my $r = ($b =~ /source(\d*)/)[0];
            $r = -1 if ($r eq "");
            int($l) <=> int($r);
        } @sources;
```

**Lines 1043-1047:** Find all source tags
- Spec can have: `Source0`, `Source1`, `Source2`, etc.
- Filter for archive files only (`.tar.gz`, `.zip`, etc.)

**Lines 1049-1055:** Sort by number
- Extract number from `Source<N>`
- Sort numerically
- `Source0` comes first, then `Source1`, etc.

---

### Lines 1057-1060: Check Exclude List
```perl
        if ( (grep $_ eq $name, @exclude) ) {
            next;
        }
```

**Skip:** If package name in exclude list

---

### Lines 1061-1068: Store Package Metadata
```perl
        $packs{$name} = {
            name => $name,
            version => $version,
            release => $release,
            deps => @buildrequires,
            subpacks => @subpacks,
            filename => $spec,
        };
```

**Hash Structure:**
- Key: Package name
- Value: Hash ref with all metadata
- Used throughout build process

---

### Lines 1071-1073: Map Sub-packages
```perl
        foreach my $sub_p (@{$packs{$name}->{subpacks}}) {
            $tmp_sub_to_main{$sub_p} = $name;
        }
        %subptomainp = %tmp_sub_to_main;
```

**Purpose:** Map binary package names to source package

**Example:**
```perl
%subptomainp = (
    'mylib' => 'mylib',
    'mylib-devel' => 'mylib',
    'mylib-docs' => 'mylib'
);
```

**Used in:** Dependency resolution
- Dependency on `mylib-devel` means dependency on source package `mylib`

---

### Lines 1075-1080: Store Main Source File
```perl
        if (@sorted) {
            $packs{$name}->{source} = basename($pack->{shift @sorted});
        }

        if ($base) {
            $packs{$name}{project_base_path} = $base;
        }
```

**Line 1076:** Store primary source tarball name
- Takes first (lowest numbered) source
- Only stores basename, not full path

**Lines 1079-1081:** Store git repository path
- Only set for git-style packages
- Used for incremental builds

---

### Lines 1085-1114: Append Missing Sub-packages from Repo
```perl
    if ($work_done == 1) {
        my @check_repos = ("$localrepo/$dist/$arch/");
        my %recal_deps = ();
        %recal_deps = recalculate_repomddeps(@check_repos);

        foreach my $miss_pack (keys %recal_deps) {
            if (grep $_ eq $miss_pack, (keys %packs)) {
                my $pushed = 0;
                my @packs_subpackages = @{$packs{$miss_pack}->{'subpacks'}};
                my @recal_rpms = @{$recal_deps{$miss_pack}};

                foreach my $miss_p (@recal_rpms) {
                  if (!(grep $_ eq $miss_p, (@packs_subpackages))) {
                    push(@packs_subpackages, $miss_p);
                    $pushed = 1;
                  }
                }

                if ($pushed == 1) {
                    @{$packs{$miss_pack}->{subpacks}} = @packs_subpackages;
                    foreach my $sub_p (@{$packs{$miss_pack}->{subpacks}}) {
                        $tmp_sub_to_main{$sub_p} = $miss_pack;
                    }
                    %subptomainp = %tmp_sub_to_main;
                }
            }
        }
    }

    return %packs;
}
```

**Purpose:** Handle packages that generate different sub-packages than spec declares

**When:** Only after first build completes (`$work_done == 1`)

**Problem:** 
- Spec may conditionally create sub-packages
- Example: `-devel` package only if certain macros defined
- Need actual built RPMs to know what was produced

**Solution:**
- Read actual RPMs from local repo
- Add any missing sub-packages
- Update mapping

**Result:** Accurate sub-package list for next iteration

---

## Repository Metadata Parsing

### The refresh_repo() Function

```perl
sub refresh_repo {
    my $rpmdeps = "$order_dir/.repo.cache";
    my (%fn, %prov, %req, %rec);
    my %exportfilters = %{$config->{'exportfilter'}};
    my %packs;
    my %ids;

    my %packs_arch;
    my %packs_done;
    open(my $fh, '<', "$rpmdeps") || die("$rpmdeps: $!\n");
```

**Purpose:** Parse `.repo.cache` and build `%repo` hash

**Variables:**
- `%fn`: Filename for each package
- `%prov`: Provides list
- `%req`: Requires list  
- `%rec`: Recommends list
- `%ids`: Package IDs (for version comparison)
- `%packs`: Final package selection per architecture

---

### Lines 1396-1459: Parse Cache File
```perl
    my ($pkgF, $pkgP, $pkgR, $pkgr);
    while(<$fh>) {
      chomp;
      if (/^F:(.*?)-\d+\/\d+\/\d+: (.*)$/) {
        my $pkgname = basename($2);
        $pkgF = $2;
        next if $fn{$1};
        $fn{$1} = $2;
        my $pack = $1;
        $pack =~ /^(.*)\.([^\.]+)$/ or die;
        push @{$packs_arch{$2}}, $1;
        my $basename = $1;
        my $arch = $2;
        for(keys %exportfilters) {
            next if ($pkgname !~ /$_/);
            for (@{$exportfilters{$_}}) {
                my $target_arch = $_;
                next if ($target_arch eq ".");
                next if (! grep ($_ eq $target_arch, @archs));
                $packs{$basename} = "$basename.$arch"
            }
        }
      } elsif (/^P:(.*?)-\d+\/\d+\/\d+: (.*)$/) {
        $pkgP = $2;
        next if $prov{$1};
        $prov{$1} = $2;
      } elsif (/^R:(.*?)-\d+\/\d+\/\d+: (.*)$/) {
        $pkgR = $2;
        next if $req{$1};
        $req{$1} = $2;
      } elsif (/^r:(.*?)-\d+\/\d+\/\d+: (.*)$/) {
        $pkgr = $2;
        next if $rec{$1};
        $rec{$1} = $2;
      } elsif (/^I:(.*?)-\d+\/\d+\/\d+: (.*)$/) {
        my $r = 0;
        if ($use_higher_deps == 1) {
          $r = 1;
        } else {
          if ($packs_done{$1}) {
            $r = 0;
          } else {
            $r = 1;
          }
        }

        if ($ids{$1} && ($r == 1) && defined($pkgF) && defined($pkgP) && defined($pkgR)) {
          my $i = $1;
          my $oldid = $ids{$1};
          my $newid = $2;
          if (Build::Rpm::verscmp($oldid, $newid) < 0) {
            $ids{$i}  = $newid;
            $fn{$i}   = $pkgF;
            $prov{$i} = $pkgP;
            $req{$i}  = $pkgR;
          }
        } else {
          next if $ids{$1};
          $ids{$1} = $2;
        }
        undef $pkgF;
        undef $pkgP;
        undef $pkgR;
      } elsif ($_ eq 'D:') {
        %packs_done = %ids;
      }
    }
    close $fh;
```

**Cache File Format:**
```
F:package.arch-123/456/0: /path/package.rpm
P:package.arch-123/456/0: package = 1.0 provides-this
R:package.arch-123/456/0: requires-that >= 2.0
r:package.arch-123/456/0: recommends-another
I:package.arch-123/456/0: package-1.0-1 123456789
D:
```

**Line-by-Line Parsing:**

**F: Filename**
- Extract package name and architecture
- Store filename
- Group packages by architecture
- Handle export filters (specific arch preferences)

**P: Provides**
- What this package provides
- Used in dependency resolution

**R: Requires**
- What this package requires
- Hard dependencies

**r: Recommends**
- Soft dependencies
- Not mandatory but suggested

**I: Package ID**
- Version and build time information
- Handle duplicate packages (keep newer version)
- `Build::Rpm::verscmp()`: RPM version comparison
- `$use_higher_deps`: Prefer higher versions across repos

**D: Delimiter**
- Marks repository boundary
- After D:, packages can't override earlier ones (unless use_higher_deps)

---

### Lines 1461-1464: Select Architecture-Specific Packages
```perl
    for my $arch (@archs) {
      $packs{$_} ||= "$_.$arch" for @{$packs_arch{$arch} || []};
    }
```

**Purpose:** Choose best architecture for each package

**Logic:**
- Iterate through compatible architectures (x86_64, i686, i586, ...)
- If package not yet selected, use this architecture's version
- First match wins (prefer more specific architecture)
