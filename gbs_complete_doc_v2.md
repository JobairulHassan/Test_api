# GBS Build Tool (Depanneur) - Complete Documentation (Part 2)

## Continuing from Repository Metadata Parsing

### Lines 1461-1464: Select Architecture-Specific Packages (continued)
```perl
    for my $arch (@archs) {
      $packs{$_} ||= "$_.$arch" for @{$packs_arch{$arch} || []};
    }
```

**Example for x86_64 build:**
```perl
# Package foo available in: x86_64, i586, noarch
# @archs = ('x86_64', 'i686', 'i586', 'i486', 'i386', 'noarch')
# Result: $packs{foo} = 'foo.x86_64' (first match)

# Package bar only available in: i586, noarch
# @archs = ('x86_64', 'i686', 'i586', 'i486', 'i386', 'noarch')
# Result: $packs{bar} = 'bar.i586' (first available)
```

**`||=` operator:** Only assign if not already set

---

### Lines 1466-1502: Build Repository Hash
```perl
    my $dofileprovides = %{$config->{'fileprovides'}};

    for my $pack (keys %packs) {
      my $r = {};
      my (@s, $s, @pr, @re, @rec);
      
      @s = split(' ', $prov{$packs{$pack}} || '');
      while (@s) {
        $s = shift @s;
        next if !$dofileprovides && $s =~ /^\//;
        if ($s =~ /^rpmlib\(/) {
          splice(@s, 0, 2);
          next;
        }
        push @pr, $s;
        splice(@s, 0, 2) if @s && $s[0] =~ /^[<=>]/;
      }
      
      @s = split(' ', $req{$packs{$pack}} || '');
      while (@s) {
        $s = shift @s;
        next if !$dofileprovides && $s =~ /^\//;
        if ($s =~ /^rpmlib\(/) {
          splice(@s, 0, 2);
          next;
        }
        push @re, $s;
        splice(@s, 0, 2) if @s && $s[0] =~ /^[<=>]/;
      }
      
      @s = split(' ', $rec{$packs{$pack}} || '');
      while (@s) {
        $s = shift @s;
        next if !$dofileprovides && $s =~ /^\//;
        if ($s =~ /^rpmlib\(/) {
          splice(@s, 0, 2);
          next;
        }
        push @rec, $s;
        splice(@s, 0, 2) if @s && $s[0] =~ /^[<=>]/;
      }
      
      $r->{'provides'} = \@pr;
      $r->{'requires'} = \@re;
      $r->{'recommends'} = \@rec;
      $repo{$pack} = $r;
    }

    Build::readdeps($config, undef, \%repo);
}
```

**Purpose:** Parse provides/requires/recommends strings into arrays

**Line 1466:** Check if file dependencies enabled
- File dependencies: `/usr/bin/python`, `/lib/libssl.so`
- Some repos don't support file-level dependencies

**Lines 1468-1502: Parse each package's dependencies**

**Provides Format:** `package = 1.0-1 package(arch) = 1.0-1 virtual-package`

**Requires Format:** `glibc >= 2.17 libssl.so.1.0.0(x86-64)`

**Parsing Logic:**
1. Split by spaces
2. Skip file paths if fileprovides disabled
3. Skip `rpmlib()` dependencies (RPM internal)
4. Add dependency name to array
5. Skip next 2 elements if version constraint (`>=`, `=`, `<`)

**Example Parsing:**
```
Input:  "glibc >= 2.17 libssl.so"
Step 1: ["glibc", ">=", "2.17", "libssl.so"]
Step 2: Take "glibc", skip ">=" and "2.17"
Step 3: Take "libssl.so"
Result: ["glibc", "libssl.so"]
```

**Lines 1499-1503:** Store in `%repo` hash

**Line 1505:** Call OBS dependency solver
- `Build::readdeps()`: Process dependencies
- Resolves virtual packages
- Builds dependency graph

**Result:** `%repo` hash ready for dependency resolution

---

## Dependency Resolution Phase

### Lines 1280-1284: Skip Package Resolution
```perl
if ($noinit == 0 && $incremental == 0) {
    resolve_skipped_packages();
}
```

**Purpose:** Determine which packages can be skipped

**Conditions to check:**
- Not in `--noinit` mode
- Not in `--incremental` mode

---

### The resolve_skipped_packages() Function

```perl
sub resolve_skipped_packages() {
    info("resolving skipped packages ...");
    
    foreach my $name (keys %to_build) {
        my $version = $to_build{$name}->{version};
        my $release = $to_build{$name}->{release};
        my $src_rpm = "$srpm_repo_path/$name-$version-$release.src.rpm";
        
        if (-f $src_rpm) {
            if ($overwrite) {
                info("*** overwriting $name-$version-$release $arch ***");
            } else {
                info("skipping $name-$version-$release $arch ");
                push(@skipped, $name);
            }
        }
    }
}
```

**Logic:**
1. Check if source RPM already exists
2. If exists and `--overwrite` specified: rebuild anyway
3. If exists and no `--overwrite`: skip this package

**Example:**
```
Local repo contains: mypackage-1.0-1.src.rpm
Current build: mypackage-1.0-1
Result: Skip (already built)

But if --overwrite specified: Rebuild anyway
```

**Result:** `@skipped` array populated with packages to skip

---

### Lines 1286-1288: Start Dependency Resolution
```perl
info("package dependency resolving ...");
update_pkgdeps($reverse_off);
update_pkgddeps();
```

**Two-phase approach:**
1. `update_pkgdeps()`: Expand full dependency tree
2. `update_pkgddeps()`: Calculate direct dependencies only

---

### The update_pkgdeps() Function

```perl
sub update_pkgdeps {
    my $rev_flag = shift;
    %tmp_expansion_errors = ();
    
    foreach my $name (keys %to_build) {
        # Skip already processed packages
        if( (grep $_ eq $name, @done) ||
            (grep $_ eq $name, @skipped) ||
            (grep $_ eq $name, @running)) {
            next;
        }
        
        if(! (grep $_ eq $name, @skipped)) {
            my $fn = $to_build{$name}->{filename};
            debug("Checking dependencies for $name");
            
            my @bdeps = expand_deps($fn, $rev_flag);
            
            if (!shift @bdeps ) {
                # First value = success flag
                debug("expansion error");
                debug("  $_") for @bdeps;
                $tmp_expansion_errors{$name} = [@bdeps];
                next;
            }
            
            my @deps;
            foreach my $depp (@bdeps) {
                my $so = source_of($depp, \%subptomainp);
                if (defined($so) && $name ne $so
                    && (! grep($_ eq $so, @skipped))
                    && (! grep($_ eq $so, @deps))) {
                    push (@deps, $so);
                }
            }
            
            $pkgdeps{$name} = [@deps];
        }
    }
}
```

**Purpose:** Calculate full dependency tree for each package

**Line 1518:** `$rev_flag`: Control reverse dependency handling
- `$reverse_off`: Don't include packages that depend on this
- `$reverse_on`: Include reverse dependencies

**Lines 1522-1525:** Skip packages already processed
- `@done`: Successfully built
- `@skipped`: Skipped (already exists)
- `@running`: Currently building

**Line 1530:** Call `expand_deps()` to get binary dependencies

**Lines 1532-1537: Handle expansion errors**
- `expand_deps()` returns array: `(success_flag, @dependencies)`
- First element: 0 = error, 1 = success
- If error: store in `%tmp_expansion_errors` for reporting
- Common errors: missing dependencies, unresolvable conflicts

**Lines 1539-1548: Map binary to source packages**
- `$depp`: Binary package name (e.g., `libssl-devel`)
- `source_of()`: Find source package (e.g., `openssl`)
- Skip self-dependencies
- Skip already skipped packages
- Remove duplicates

**Line 1550:** Store final dependency list

**Result:** `%pkgdeps{$package} = [@all_dependencies]`

---

### The expand_deps() Function

```perl
sub expand_deps {
    my ($spec, $rev_flag) = @_;
    my ($packname, $packvers, $subpacks, @packdeps);
    $subpacks = [];

    if ($spec) {
      my $d;
      if ($spec =~ /\.kiwi$/) {
        # Kiwi image special case
        $d = {
          'deps' => [ 'kiwi', 'zypper', 'createrepo', 'squashfs' ],
          'subpacks' => [],
        };
      } else {
        $d = Build::parse($config, $spec);
      }
      
      $packname = $d->{'name'};
      $packvers = $d->{'version'};
      $subpacks = $d->{'subpacks'};
      @packdeps = @{$d->{'deps'} || []};
      
      if ($rev_flag == $reverse_off) {
          if ($d->{'prereqs'}) {
            my %deps = map {$_ => 1} (@packdeps, @{$d->{'subpacks'} || []});
            push @packdeps, grep {!$deps{$_} && !/^%/} @{$d->{'prereqs'}};
          }
      }
    }

    my @extradeps = ();
    if ($vmtype eq "kvm") {
       push @packdeps, @{$config->{'vminstall'}};
    }
    
    my @bdeps = Build::get_build($config, $subpacks, @packdeps, @extradeps);

    return @bdeps;
}
```

**Purpose:** Expand spec file BuildRequires into full dependency list

**Lines 1552-1560: Parse spec file**
- `.kiwi` files: Special image build files
- Normal specs: Parse with `Build::parse()`

**Lines 1568-1574: Add prerequisites**
- Prerequisites: Must be installed before main dependencies
- Example: `Requires(pre): /bin/sh`
- Only included if not building reverse dependencies

**Lines 1577-1580: Add VM dependencies**
- KVM builds need additional packages
- Example: `kvm-tools`, `qemu`

**Line 1582:** Call OBS build dependency resolver
- `Build::get_build()`: Main dependency resolution function
- Input: config, sub-packages, dependencies
- Output: Array with success flag and full dependency list

**Return Format:**
```perl
# Success:
(1, 'glibc', 'gcc', 'make', 'autoconf', ...)

# Failure (missing dependency):
(0, 'missing: libfoo-devel', 'missing: libbar >= 2.0')
```

---

### The get_deps() Function

```perl
sub get_deps {
    my $spec  = shift;
    my @bdeps = ();
    my @ndeps = ();
    my @deps  = ();
    my $d     = Build::parse($config, $spec);

    @deps = @{$d->{'deps'} || []};
    
    @ndeps = grep {/^-/} @deps;
    my %ndeps = map {$_ => 1} @ndeps;
    @deps = grep {!$ndeps{$_}} @deps;
    
    if ($d->{'prereqs'}) {
        my %deps = map {$_ => 1} (@deps, @{$d->{'subpacks'} || []});
        push @deps, grep {!$deps{$_} && !/^%/} @{$d->{'prereqs'}};
    }
    
    @deps = Build::do_subst($config, @deps);
    @deps = map {s/\s*[<=>]+.*$//s; $_} @deps;
    
    foreach my $pack (@deps) {
        next if !defined($pack);
        my $pkg;
        my $found = 0;
        foreach my $pkg (keys %repo) {
            my @prov = @{$repo{$pkg}->{'provides'}};
            if (grep $_ eq $pack, @prov ){
                push (@bdeps, $pkg);
                last;
            }
        }
    }
    
    return @bdeps;
}
```

**Purpose:** Get DIRECT dependencies only (not transitive)

**Lines 1549-1551:** Parse spec and extract dependencies

**Lines 1553-1555: Handle negative dependencies**
- Format: `-package-to-exclude`
- Used to exclude automatically added dependencies

**Lines 1557-1560:** Add prerequisites

**Line 1562:** Substitute RPM macros
- Example: `%{name}-devel` → `mypackage-devel`

**Line 1563:** Remove version constraints
- `glibc >= 2.17` → `glibc`
- We only care about package names, not versions

**Lines 1565-1576: Map to repository packages**
- Search `%repo` for packages providing this dependency
- May be provided by different package name
- Example: `/usr/bin/python` provided by `python3` package

**Result:** Array of direct dependencies as source package names

---

### The update_pkgddeps() Function

```perl
sub update_pkgddeps {
    %pkgddeps = ();
    
    foreach my $name (keys %to_build) {
        if(! (grep $_ eq $name, @skipped) &&
           ! (grep $_ eq $name, @done)) {
            my $fn = $to_build{$name}->{filename};
            my @bdeps = get_deps($fn);
            
            my @deps;
            foreach my $depp (@bdeps) {
                my $so = source_of($depp, \%subptomainp);
                if (defined($so) && $name ne $so &&
                    (! grep($_ eq $so, @skipped)) &&
                    (! grep($_ eq $so, @done)) &&
                    (! grep($_ eq $so, @deps))) {
                    push (@deps, $so);
                }
            }
            
            $pkgddeps{$name} = [@deps];
        }
    }
    
    # Initialize reverse dependencies
    for my $pack (sort keys %pkgddeps) {
        $pkgrddeps{$pack} = [];
    }
    
    # Build reverse dependency map
    for my $pack (sort keys %pkgddeps) {
        next if (! defined($pkgddeps{$pack}));
        for (@{$pkgddeps{$pack} }) {
            push @{$pkgrddeps{$_}}, $pack;
        }
    }
}
```

**Purpose:** Calculate direct dependencies and reverse dependencies

**Lines 1652-1668: Build direct dependency map**
- Similar to `update_pkgdeps()` but uses `get_deps()`
- `get_deps()`: Returns direct dependencies only
- Result: `%pkgddeps{$package} = [@direct_dependencies]`

**Lines 1671-1673:** Initialize reverse dependencies hash
- Every package gets empty array initially

**Lines 1676-1680: Build reverse dependency map**
- For each package's dependencies
- Add this package to dependency's reverse list
- Example: If `A` depends on `B`, then `B`'s reverse deps include `A`

**Result:**
```perl
%pkgddeps = (
    'app' => ['libfoo', 'libbar'],
    'libfoo' => [],
    'libbar' => ['libfoo']
);

%pkgrddeps = (
    'app' => [],
    'libfoo' => ['app', 'libbar'],
    'libbar' => ['app']
);
```

---

### Topological Sorting

### The get_top_order() Function

```perl
sub get_top_order {
    my @all_queue=();
    my @queue = ();
    my @top_order = ();
    my %ref_build_complete = ();
    my $pkg_number = 0;
    
    for my $pack (sort keys %pkgddeps) {
        push @all_queue, $pack;
        $pkg_number++;
        $ref_build_complete{$pack} = 0;
        
        my $pack_in_degree = 0;
        if (defined $pkgddeps{$pack}) {
            $pack_in_degree = @{$pkgddeps{$pack}};
        }
        
        if ($pack_in_degree == 0) {
            push @queue, $pack;
        }
    }
```

**Purpose:** Calculate build order using BFS topological sort

**Algorithm:** Kahn's algorithm for topological sorting

**Lines 1583-1598: Initialize**
- `@all_queue`: All packages (for verification)
- `@queue`: Packages with no dependencies (ready to build)
- `@top_order`: Result array (sorted build order)
- `%ref_build_complete`: Count satisfied dependencies

**In-degree:** Number of dependencies
- 0 dependencies: Can build immediately
- 1+ dependencies: Must wait for dependencies to build

---

### Lines 1599-1610: BFS Traversal
```perl
    while(@queue) {
        my $cur_pack = shift @queue;
        push @top_order, $cur_pack;
        
        for (@{$pkgrddeps{$cur_pack}}) {
            $ref_build_complete{$_} += 1;
            
            if (@{$pkgddeps{$_}} == $ref_build_complete{$_}) {
                push @queue, $_;
            }
        }
    }
```

**Algorithm Steps:**
1. Take package from queue (no dependencies remaining)
2. Add to build order
3. Update packages that depend on this one
4. If all dependencies satisfied, add to queue

**Example:**
```
Packages: A, B, C, D
Dependencies: A→[], B→[A], C→[A], D→[B,C]

Step 1: Queue=[A], Order=[]
Step 2: Queue=[], Order=[A], B and C ready
Step 3: Queue=[B,C], Order=[A]
Step 4: Queue=[C], Order=[A,B]
Step 5: Queue=[], Order=[A,B,C], D ready
Step 6: Queue=[D], Order=[A,B,C]
Step 7: Queue=[], Order=[A,B,C,D]
```

---

### Lines 1613-1625: Circular Dependency Detection
```perl
    %left_pkg=();
    @left_pkg{@all_queue}=();
    delete @left_pkg{@all_queue};

    if(check_circle() == 0) {
        info("there is no circle in $pkg_number packages");
        return @top_order;
    }
    else {
        info("circle found in $pkg_number packages, exit...");
        exit 1;
    }
}
```

**Purpose:** Detect circular dependencies

**Lines 1613-1615: Find unprocessed packages**
- `@all_queue`: All packages
- `@top_order`: Successfully sorted packages
- `%left_pkg`: Packages not in topological order
- If any left: Circular dependency exists

**Line 1617:** Call `check_circle()` for detailed analysis

---

### The check_circle() Function

```perl
sub check_circle {
    my $pkg;
    my $reset_visit = sub {
        for my $pkg (keys %pkgddeps) {
            $visit{$pkg} = 0;
        }
    };
    
    for $pkg (keys %left_pkg) {
        my @visit_stack;
        &$reset_visit();
        push (@visit_stack, $pkg);
        $visit{$pkg} = 1;
        
        if (find_circle(@visit_stack) == 1) {
            return 1;
        }
    }

    return 0;
}
```

**Purpose:** Use DFS to find and report circular dependencies

**Algorithm:**
1. For each unprocessed package
2. Start DFS traversal
3. If cycle found, return 1
4. Reset visited flags between attempts

---

### The find_circle() Function

```perl
sub find_circle {
    my (@stack) = @_;
    my $curpkg = $stack[$#stack];

    my @deps = @{$pkgddeps{$curpkg}};
    my $dep;

    foreach my $dep (@deps) {
        if ($visit{$dep} == 1 && ! (grep $_ eq $dep, @stack)){
            next;
        }
        
        $visit{$dep} = 1;
        
        if (grep $_ eq $dep, @stack){
            my @circle = ();
            push @circle, $dep;
            
            while (@stack) {
                my $cur = pop @stack;
                unshift @circle, $cur;
                last if ($cur eq $dep);
            }
            
            warning ("circle found: " . join("->", @circle));
            return 1;
        } else {
            push (@stack, $dep);
            return 1 if (find_circle(@stack) == 1);
            pop @stack;
        }
    }

    return 0;
}
```

**Purpose:** DFS to find circular dependency path

**Algorithm:**
1. Visit each dependency of current package
2. If dependency already in stack: CYCLE FOUND
3. Otherwise: Recursively check dependency
4. Backtrack if no cycle found

**Example Cycle Detection:**
```
Package A depends on B
Package B depends on C
Package C depends on A

DFS: A → B → C → A (cycle!)
Output: "circle found: A->B->C->A"
```

**Why This Matters:**
- Circular dependencies can't be built
- Must be fixed before building
- Common in development, rare in production

---

### Lines 1627-1672: Expand Transitive Dependencies

```perl
# Expand dependency using direct dependency dict
# pkgddeps  => pkgdeps
# pkgrddeps => pkgrdeps

%pkgdeps = ();
%pkgrdeps = ();

for my $pkg (keys %pkgddeps) {
    $pkgdeps{$pkg} = [@{$pkgddeps{$pkg}}]
}

for my $pkg (keys %pkgrddeps) {
    $pkgrdeps{$pkg} = [@{$pkgrddeps{$pkg}}]
}

for my $pkg (reverse @top_order) {
    next if (! defined($pkgddeps{$pkg}));
    for (@{$pkgddeps{$pkg}}) {
        push @{$pkgrdeps{$_}}, @{$pkgrdeps{$pkg}};
        my %uniq_deps = map {$_,1} @{$pkgrdeps{$_}};
        $pkgrdeps{$_} = [keys(%uniq_deps)];
    }
}

for my $pkg (@top_order) {
    next if (! defined($pkgrddeps{$pkg}));
    for (@{$pkgrddeps{$pkg}}) {
        push @{$pkgdeps{$_}}, @{$pkgdeps{$pkg}};
        my %uniq_deps = map {$_,1} @{$pkgdeps{$_}};
        $pkgdeps{$_} = [keys(%uniq_deps)];
    }
}
```

**Purpose:** Calculate transitive closure of dependencies

**Initial State (direct only):**
```
A depends on: B
B depends on: C
C depends on: []
```

**Lines 1640-1647: Initialize with direct dependencies**

**Lines 1649-1655: Expand reverse dependencies (bottom-up)**
- Process in reverse topological order (C, B, A)
- C: No dependencies, nothing to propagate
- B: Add B's reverse deps to C's reverse deps
- A: Add A's reverse deps to B's and C's reverse deps

**Lines 1657-1663: Expand forward dependencies (top-down)**
- Process in topological order (A, B, C)
- A: Add A's deps to B's deps
- B: Add B's deps to C's deps

**Final State (transitive):**
```
%pkgdeps = (
    'A' => ['B', 'C'],    # A depends on B and C
    'B' => ['C'],          # B depends on C
    'C' => []              # C has no dependencies
);

%pkgrdeps = (
    'A' => [],             # Nothing depends on A
    'B' => ['A'],          # A depends on B
    'C' => ['A', 'B']      # A and B depend on C
);
```

**Use Case:**
- Full deps: "Build everything A needs before building A"
- Full reverse deps: "If C changes, rebuild A and B"

---

## Binary List Resolution

### Lines 1290-1314: Handle --binary-list Option

```perl
my @bins = get_binary_list();
if (@bins) {
    my @tobuild = ();
    my @final = ();

    foreach my $b (@bins) {
        next if $b eq "";
        my $found = 0;
        
        foreach my $name (keys %packs) {
            my @sp = @{$packs{$name}->{subpacks}};
            my $debuginfo = $b;
            $debuginfo =~ s/(.*)-debuginfo/$1/;
            $debuginfo =~ s/(.*)-debugsource/$1/;
            $debuginfo =~ s/(.*)-docs/$1/;
            
            my $nb;
            if ($b ne $debuginfo) {
                $nb = $debuginfo;
            } else {
                $nb = $b;
            }
            
            if ( grep $_ eq $nb, @sp ) {
                push(@tobuild, $name);
                $found = 1 ;
                last;
            }
        }
        
        if (!$found) {
            push(@tofind, $b);
        }
    }
```

**Purpose:** When user specifies binary packages, find source packages

**get_binary_list():** Combines `--binary-list` and `--binary-from-file`

**Lines 1295-1319: Map binary to source**
- User specifies: `mylib-devel`
- Need to find: `mylib` (source package)
- Special handling for `-debuginfo`, `-debugsource`, `-docs` suffixes
- These are auto-generated, strip suffix to find base name

**Example:**
```
User specifies: libfoo-devel, libbar-docs
Source packages: libfoo produces (libfoo, libfoo-devel)
                 libbar produces (libbar, libbar-docs)
Result: Build libfoo and libbar
```

---

### Lines 1321-1331: Resolve Dependencies
```perl
    push @final, resolve_deps(\@tobuild, $deps_build, $rdeps_build, %packs);
    %to_build = parse_packs($config, @final);

    @skipped = ();
    if ($noinit == 0 && $incremental == 0) {
        resolve_skipped_packages();
    }
    
    $get_order = 0;
    update_pkgdeps($reverse_off);
    update_pkgddeps();
}
```

**Purpose:** Build dependency tree for specified binaries

**Line 1321:** `resolve_deps()` 
- Input: Packages to build, flags for deps/rdeps
- Output: Full list including dependencies
- `$deps_build`: Include forward dependencies
- `$rdeps_build`: Include reverse dependencies

**Lines 1322-1331:** Recalculate for subset
- Re-parse only needed packages
- Re-resolve skip list
- Recalculate dependencies
- Updates `@build_order`

---

## Pre-Build Validation

### Lines 1333-1334: Check Package Count
```perl
warning("no available packages to build.") if (scalar (keys %to_build) == 0);
```

**Stop if:** No packages left after filtering

---

### Lines 1336-1342: Mode-Specific Validation
```perl
if ($incremental == 1 && scalar(keys %to_build) > 1) {
    error("incremental build only support building one package");
}

if ($noinit == 1 && scalar(keys %to_build) > 1) {
    error("--noinit build only support building one package");
}
```

**Incremental Build:** Mounts source directory in build root
- Can't mount multiple directories in same build root
- Solution: Build one package at a time

**No-init Build:** Reuses existing build root
- Build root configured for specific package
- Solution: Build one package at a time

---

## Worker Thread Pool Setup

### Lines 1345-1348: Initialize Workers
```perl
for(my $w = 0; $w < $MAX_THREADS; $w++) {
    $workers{$w} = { 'state' => 'idle' , 'tid' => undef };
}
```

**Purpose:** Create thread pool

**For `--threads 8`:**
```perl
%workers = (
    0 => { state => 'idle', tid => undef },
    1 => { state => 'idle', tid => undef },
    2 => { state => 'idle', tid => undef },
    3 => { state => 'idle', tid => undef },
    4 => { state => 'idle', tid => undef },
    5 => { state => 'idle', tid => undef },
    6 => { state => 'idle', tid => undef },
    7 => { state => 'idle', tid => undef }
);
```

**States:**
- `idle`: Worker available for new job
- `busy`: Worker currently building package
- `tid`: Thread ID when busy

---

### Lines 1350-1355: Create Initial Repository
```perl
if ( ! -e "$rpm_repo_path" ) {
    info("creating repo...");
    createrepo ($arch, $dist);
}
```

**Purpose:** Initialize repository metadata

**createrepo:** Creates `repodata/` directory with XML metadata
- `repomd.xml`: Master index
- `primary.xml.gz`: Package information
- `filelists.xml.gz`: File listings
- `other.xml.gz`: Changelog, etc.

---

### Lines 1358-1367: Signal Handlers
```perl
$SIG{'INT'} = $SIG{'TERM'} = sub {
    print("^C captured\n");
    $TERM=1;
};

$SIG{'ALRM'} = sub {
    if (my_system("sudo /bin/echo -n") != 0) {
        error("sudo: failed to request passwd")
    } else {
        alarm(SUDOV_PERIOD);
    }
};

kill 'ALRM', $;
```

**Purpose:** Handle interrupt signals and keep sudo alive

**Lines 1358-1361: Ctrl+C Handler**
- `$SIG{'INT'}`: Ctrl+C signal
- `$SIG{'TERM'}`: Termination signal
- Sets `$TERM = 1`: Tells all threads to stop gracefully
- Prevents abrupt termination leaving build roots in bad state

**Lines 1363-1369: Sudo Keep-Alive**
- `$SIG{'ALRM'}`: Alarm signal (timer)
- Tests sudo access with harmless echo command
- If successful: Set another alarm for 3 minutes later
- If failed: Exit with error (sudo timeout)
- Prevents sudo timeout during long builds

**Line 1371:** Trigger first alarm immediately
- `kill 'ALRM', $`: Send ALRM signal to self
- `$`: Current process ID
- Starts the keep-alive cycle

**Why This Matters:**
- Builds can take hours
- Sudo timeout is usually 15 minutes
- Without keep-alive: Build fails mid-way with permission errors

---

### Lines 1374-1377: Mount Safety Check
```perl
for(my $i = 0; $i < $MAX_THREADS; $i++) {
    mount_source_check("$scratch_dir.$i");
}
```

**Purpose:** Verify no directories mounted in build roots

**Why:** 
- Previous build may have crashed
- Left source directories mounted
- If we delete build root: Deletes source code!

---

### The mount_source_check() Function

```perl
sub mount_source_check {
    my $build_root = canonpath(shift);
    my @mount_list;

    open my $file, '<', "/proc/self/mountinfo" or die $!;
    while (<$file>) {
        chomp;
        next if ($_ !~ /$build_root/);
        my @mount_info= split(' ', $_);
        push @mount_list, "$mount_info[3] ==> $mount_info[4]";
    }

    if (@mount_list) {
        error("there're mounted directories to build root. Please unmount them " .
              "manually to avoid being deleted unexpectly:\n\t" . 
              join("\n\t", @mount_list));
    }
}
```

**Purpose:** Check `/proc/self/mountinfo` for mounts in build root

**File Format:**
```
36 35 8:1 /source /build/root/source rw,relatime - ext4 /dev/sda1 rw
```

**Fields:**
- Field 3: Source path
- Field 4: Mount point

**Action:** If any mounts found, exit with error
- User must manually unmount
- Prevents data loss

---

### Lines 1380-1394: Scan Existing Local Packages
```perl
for my $pkg (`find "$rpm_repo_path" -type f -name "*.rpm" 2>/dev/null`) {
    $pkg =~ s/\n//;
    my ($name, $version, $release, $arch) = get_pkg_info $pkg;
    next if $name eq '';
    my $na = "$name$arch";
    
    if (exists $rpmpaths{$na}) {
        push @{$rpmpaths{$na}}, $pkg;
    } else {
        $rpmpaths{$na} = [$pkg];
    }
}

for my $pkg (`find "$srpm_repo_path" -type f -name "*.rpm" 2>/dev/null`) {
    $pkg =~ s/\n//;
    my ($name, $version, $release, $arch) = get_pkg_info $pkg;
    next if $name eq '';
    my $na = "$name$arch";
    
    if (exists $srpmpaths{$na}) {
        push @{$srpmpaths{$na}}, $pkg;
    } else {
        $srpmpaths{$na} = [$pkg];
    }
}
```

**Purpose:** Build index of existing RPM files

**get_pkg_info():** Extracts metadata from filename
```perl
sub get_pkg_info {
    my $package = shift;
    if ($package =~ /\/([^\/]+)-([^-]+)-([^-]+)\.(\w+)\.rpm$/) {
        return ($1, $2, $3, $4);  # name, version, release, arch
    } else {
        return;
    }
}
```

**Example:**
```
Input:  /path/mylib-1.0-1.x86_64.rpm
Output: ('mylib', '1.0', '1', 'x86_64')
```

**Data Structure:**
```perl
%rpmpaths = (
    'mylib.x86_64' => [
        '/path/mylib-1.0-1.x86_64.rpm',
        '/path/mylib-1.0-2.x86_64.rpm'
    ]
);
```

**Used For:** Removing old versions after successful build

---

## Special Modes (--noinit and --incremental)

### Lines 1397-1407: Handle Special Build Modes
```perl
if ($noinit == 1 || $incremental == 1) {
    my $ret = 0;
    for my $pkg (keys %to_build) {
        $ret = worker_thread($pkg, 0, 1);
        last;
    }
    update_repo();
    build_report();
    exit $ret;
}
```

**Purpose:** Single-threaded build for special modes

**No-Init Mode (`--noinit`):**
- Reuse existing build root
- No initialization
- Fast for repeated builds
- Single package only

**Incremental Mode (`--incremental`):**
- Mount source directory in build root
- Edit source during build
- Useful for debugging
- Single package only

**Lines 1399-1402:** Build the one package
- Worker 0 (first build root)
- Index 1 (first in sequence)
- Returns exit code directly

**Lines 1403-1405:** Cleanup and exit
- Update repository metadata
- Generate reports
- Exit with build status

---

## Main Build Loop

This is the heart of the build system - the parallel build orchestration.

### Lines 1413-1417: Loop Setup
```perl
while (! $TERM) {
    my @order = ();
    my @order_clean = ();
    
    set_idle_of_all_finished_thread();
    my $no_of_idles = no_of_idle_thread();
```

**Main Loop:** Runs until `$TERM` flag set

**Per Iteration:**
1. Find packages ready to build
2. Spawn threads for available workers
3. Wait for threads to finish
4. Update dependencies when packages complete

**Line 1416:** Check which threads finished
**Line 1417:** Count available workers

---

### The set_idle_of_all_finished_thread() Function

```perl
sub set_idle_of_all_finished_thread {
    foreach my $w (sort { $a <=> $b } keys %workers) {
        my $tid = $workers{$w}->{tid};
        
        if (! defined(threads->object($tid))) {
            set_idle($w);
        }
    }
}
```

**Purpose:** Mark completed threads as idle

**threads->object($tid):** Returns thread object if exists
- Defined: Thread still running
- Undef: Thread finished and detached

**set_idle():** Updates worker state
```perl
sub set_idle {
    my $worker = shift;
    $workers{$worker} = { 'state' => 'idle' , 'tid' => undef};
}
```

---

### The no_of_idle_thread() Function

```perl
sub no_of_idle_thread {
    set_idle_of_all_finished_thread();
    my @idle_workers  = ();
    
    foreach my $w (sort { $a <=> $b } keys %workers) {
        if ( $workers{$w}->{state} eq 'idle' ) {
            push (@idle_workers, $w);
        }
    }
    
    return scalar @idle_workers;
}
```

**Purpose:** Count available workers

**Returns:** Number between 0 and $MAX_THREADS

---

### Lines 1419-1423: Dependency Update Check
```perl
    {
        lock($DETACHING);
        
        if ($dirty) {
            create_cache_local();
            refresh_repo();
            update_expansion_errors();
            $dirty = 0;
        }
```

**Critical Section:** Protected by lock

**Dirty Flag:** Set when package finishes building
- Means: New RPMs available in local repo
- Action: Refresh repository metadata
- Result: Other packages can now satisfy dependencies

**Line 1421:** `create_cache_local()` - Rescan local repo
**Line 1422:** `refresh_repo()` - Reload all metadata
**Line 1423:** `update_expansion_errors()` - Retry failed resolutions

---

### The create_cache_local() Function

```perl
sub create_cache_local {
    my_system("'$build_dir'/createdirdeps '$rpm_repo_path' > '$order_dir'/.repo.cache.local ");
    my_system("echo D: >> '$order_dir'/.repo.cache.local");
    my_system("cat '$order_dir'/.repo.cache.local '$order_dir'/.repo.cache.remote >'$order_dir'/.repo.cache");
}
```

**Purpose:** Regenerate local repository cache

**Steps:**
1. Scan local RPMs with `createdirdeps`
2. Add delimiter
3. Merge with remote cache

**Why Needed:** New packages built, metadata outdated

---

### The update_expansion_errors() Function

```perl
sub update_expansion_errors {
    my %new_expansion_errors = ();
    
    foreach my $name (%tmp_expansion_errors) {
        next if(! defined($to_build{$name}) );
        
        my $fn = $to_build{$name}->{filename};
        my @bdeps = expand_deps($fn, $reverse_off);
        
        if (!shift @bdeps ) {
            $new_expansion_errors{$name} = [@bdeps];
        }
    }
    
    %tmp_expansion_errors = %new_expansion_errors;
}
```

**Purpose:** Retry dependency resolution for failed packages

**Logic:**
- Package A failed because missing dependency B
- B just finished building
- Retry A's dependency resolution
- If now succeeds: Remove from error list

---

### Lines 1425-1461: Find Ready Packages
```perl
        foreach my $name (@build_order) {
            if( ! (grep $_ eq $name, @done) &&
                ! (grep $_ eq $name, @skipped) &&
                ! (grep $_ eq $name, @running))
            {
                next if (exists $tmp_expansion_errors{$name});
                
                my @bdeps = @{$pkgddeps{$name}};
                my $add = 1;
                
                foreach my $depp (@bdeps) {
                    if ((! grep($_ eq $depp, @skipped)) &&
                        (! exists $expansion_errors{$depp}) &&
                        (! grep($_ eq $depp, @done))) {
                        $add = 0;
                        last;
                    }
                }
                
                if ($add == 1 ) {
                    push(@order, $name);
                    
                    if ($no_of_idles <= scalar @order) {
                        last;
                    }
                }
            } else {
                push(@order_clean, $name);
            }
        }
```

**Purpose:** Find packages ready to build

**Iterate through topological order** (dependencies first)

**Skip if:**
- Already done (`@done`)
- Skipped (`@skipped`)
- Currently running (`@running`)
- Has expansion errors

**Check dependencies:**
- All dependencies must be done or skipped
- If any dependency pending: Not ready yet

**Add to queue:**
- Package ready: Add to `@order`
- Stop when queue size equals available workers

**Line 1457-1459:** Clean up build order
- Remove processed packages from `@build_order`
- Keeps array smaller for next iteration

---

### Lines 1463-1474: Check Termination Conditions
```perl
        if (@order == 0 && threads->list() == 0 && $dirty == 0) {
            %expansion_errors = ();
            @expansion_errors{keys %tmp_expansion_errors} = values %tmp_expansion_errors;
            
            if (scalar(keys %to_build) == @done + @skipped +
                scalar(keys %expansion_errors) && !$dirty) {
                $TERM = 1;
            }
        }
    }

    last if ($TERM);

    if (@order == 0) {
        sleep(0.1);
        next;
    }
```

**Termination Conditions:**
1. No packages ready to build
2. No threads running
3. No dirty flag (dependencies up-to-date)

**Check if all packages accounted for:**
```
Total packages = Done + Skipped + Expansion Errors
```

**If not all done:**
- Some packages waiting for dependencies
- Sleep briefly and retry

**Lines 1476-1477:** Exit loop if termination flag set

**Lines 1479-1482:** No ready packages but threads running
- Wait for threads to finish
- May free up more packages

---

### Lines 1484-1486: Dry Run Mode
```perl
    if ($dryrun) {
        exit 1
    }
```

**Purpose:** Show build order without building

**Output Already Displayed:**
- Topological sort completed
- Build order shown

**Exit:** Mission accomplished

---

### Lines 1491-1529: Spawn Build Threads
```perl
    while (@order && ! $TERM) {
        my $needed = $MAX_THREADS - threads->list();
        
        if ($needed == 0) {
            sleep(0.1);
            next;
        }
        
        for (; $needed && ! $TERM; $needed--) {
            my $job ;
            if (scalar (@order) != 0) {
                $job = shift(@order);
            }
            else {
                last ;
            }

            my $worker = find_idle();
            my $index;
            
            {
                lock($DETACHING);
                push (@running, $job);
                $index = scalar(@done) + scalar(@running);
            }
            
            my $thr = threads->create(\&worker_thread, $job, $worker, $index);
            my $tid = $thr->tid();
            set_busy($worker, $tid);
        }
    }
}
```

**Outer Loop:** While packages in queue and not terminated

**Line 1492:** Calculate threads needed
- `$MAX_THREADS`: Maximum allowed (e.g., 8)
- `threads->list()`: Currently running
- `$needed`: How many more we can start

**Lines 1494-1497:** All workers busy
- Wait briefly for one to finish

**Lines 1499-1528: Inner loop - spawn threads**

**Line 1501-1507:** Get next package from queue
- If queue empty: Exit inner loop

**Line 1509:** Find available worker ID

**Lines 1512-1516: Critical section**
- Add to `@running` list
- Calculate sequence index for display
- Protected by lock

**Line 1518:** Create new thread
- Function: `worker_thread`
- Parameters: package name, worker ID, index
- Returns thread object

**Line 1519-1520:** Mark worker as busy
- Store thread ID
- Update worker state

---

### The find_idle() Function

```perl
sub find_idle {
    my $idle = -1;
    set_idle_of_all_finished_thread();
    
    foreach my $w (sort { $a <=> $b } keys %workers) {
        if ( $workers{$w}->{state} eq 'idle' ) {
            $idle = $w;
            last;
        }
    }
    
    return $idle;
}
```

**Purpose:** Find first available worker

**Returns:** Worker ID (0-7 for 8 threads) or -1 if none

---

### The set_busy() Function

```perl
sub set_busy {
    my $worker = shift;
    my $thread = shift;
    $workers{$worker} = { 'state' => 'busy', 'tid' => $thread };
}
```

**Purpose:** Mark worker as busy with thread ID

---

## Worker Thread Execution

### The worker_thread() Function

```perl
sub worker_thread {
    my ($name, $thread, $index) = @_;
    
    debug("call build process:");
    my $status;
    
    eval {
        $status = build_package($name, $thread, $index);
    };
    
    if ($@) {
        warning("$@");
        $status = -1;
    }

    {
        lock($DETACHING);
        my $version = $to_build{$name}->{version};
        my $release = $to_build{$name}->{release};
        
        threads->detach() if ! threads->is_detached();
        
        @running = grep { $_ ne "$name"} @running;
        push(@done, $name);
        
        if ($status == 0) {
            $dirty = 1;
        }
        
        if ($fail_fast && $status == 1) {
            info("build failed, exit...");
            $TERM = 1;
        }

        if ($keepgoing eq "off" && $status == 1) {
            info("build failed, exit...");
            $TERM = 1;
        }
    }

    debug("*** build $name exit with status($status), is dirty:$dirty, (worker: $thread) ***");
    return $status;
}
```

**Purpose:** Thread entry point for building one package

**Parameters:**
- `$name`: Package name to build
- `$thread`: Worker ID (0-7)
- `$index`: Sequence number for display

**Lines 2109-2116: Execute build**
- `eval{}`: Catch any Perl errors
- Calls `build_package()` which does actual work
- Returns status: 0=success, 1=failure, -1=error

**Lines 2118-2143: Critical section**
- Protected by lock (thread-safe)
- Detach thread (don't need to join)
- Move from `@running` to `@done`
- Set dirty flag if successful
- Check fail-fast and keepgoing options

**Status Codes:**
- `0`: Build succeeded
- `1`: Build failed (rpmbuild error)
- `-1`: Internal error (Perl exception)

---

## The build_package() Function - Core Build Logic

This is the most important function - it actually builds the package.

### Lines 2183-2190: Setup
```perl
sub build_package {
    my ($name, $thread, $index) = @_;
    use vars qw(@package_repos);

    my $version = $to_build{$name}->{version};
    my $release = $to_build{$name}->{release};
    my $spec_name = basename($to_build{$name}->{filename});
    my $pkg_path = "$build_root/local/sources/$dist/$name-$version-$release";
```

**Extract package information:**
- Version, release from metadata
- Spec filename
- Path to exported source

---

### Lines 2191-2203: Determine Spec File Path
```perl
    my $srpm_filename = "";
    my $not_ex = 0;
    
    if ( ( $style eq "git" || $style eq "tar" ) && $incremental == 0 ) {
        if ($not_export_source == 1) {
            $not_ex = grep /^$name$/, @not_export;
            if ($vmtype eq "kvm") {
               $not_ex = 0;
            }
            if ($not_ex) {
                $srpm_filename = $to_build{$name}->{filename};
            } else {
                $srpm_filename = "$pkg_path/$spec_name";
            }
        } else {
            $srpm_filename = "$pkg_path/$spec_name";
        }
    } else {
        $srpm_filename = $to_build{$name}->{filename};
    }
```

**Logic:**
- Normally: Use exported spec in `$pkg_path`
- If no-export optimization: Use original spec location
- If incremental: Use original spec location

---

### Lines 2205-2209: Check Termination
```perl
    my @args = ();
    my @args_inc = ();
    
    if ($TERM == 1) {
        return -1;
    }
```

**Early exit:** If termination requested, don't start build

---

### Lines 2210-2225: Build Command Basics
```perl
    push @args, "sudo /usr/bin/build";
    push @args, "--uid $zuid:$zgid" if ($zuid != 0 && $zgid != 0);
    
    my $nprocessors = 2;
    if ($^O eq "linux") {
        $nprocessors = int(int(sysconf(SC_NPROCESSORS_ONLN))/int($MAX_THREADS));
        if ($nprocessors < 1) {
            $nprocessors = 1;
        }
    } else {
        warning("depanneur only support linux platform");
    }
    
    my $target_arch=`$build_dir/queryconfig target --dist '$dist' --configdir '$dist_configs' --archpath '$arch'`;
    chomp $target_arch;
    if ($target_arch eq "") {
        push @args, "--target $arch";
    } else {
        push @args, "--target $target_arch";
    }
```

**Line 2210:** Base command - OBS build script

**Line 2211:** Run as correct user
- Build shouldn't run as root
- Files owned by correct user

**Lines 2213-2221: Calculate parallel jobs**
- Total CPUs / Total threads = Jobs per thread
- Example: 32 CPUs / 8 threads = 4 jobs per thread
- Minimum 1 job per thread

**Lines 2223-2229: Target architecture**
- Query config for actual target
- May differ from build architecture
- Example: Build on x86_64, target i586

---

### Lines 2230-2258: Build Options
```perl
    push @args, "--jobs " . $nprocessors * 2;
    push @args, "--no-init" if ($noinit == 1);
    push @args, "--keep-packs" if ($keep_packs == 1);
    push @args, "--use-higher-deps" if ($use_higher_deps == 1);
    push @args, "--cachedir '$cache_dir'";
    push @args, "--dist '$dist_configs'/$dist.conf";
    push @args, "--arch '$archpath'";
    push @args, "'$srpm_filename'";
    push @args, "--ccache" if ($ccache);
    
    if (! $pkg_ccache eq "") {
        push @args, "--pkg-ccache '$pkg_ccache'";
    }
    
    push @args, "--icecream '$icecream'" if ($icecream);
    push @args, "--baselibs" if ($create_baselibs);
    
    if (! $extra_packs eq "") {
        my $packs = join(' ', split(',', $extra_packs));
        push @args, "--extra-packs=\"$packs\"";
    }

    # Check buildflags for ccache
    my @buildflags=`$build_dir/queryconfig buildflags+ useccache --dist '$dist' --configdir '$dist_configs' --archpath '$arch'`;
    if (grep ($_ eq $name, grep(s/\s*$//g, @buildflags))) {
        push @args, "--ccache";
    }
```

**Key Options:**

**`--jobs N`:** Parallel make jobs
- Set to 2x processor count
- Example: 4 CPUs → `-j8`

**`--no-init`:** Skip build root init
- Faster for repeated builds

**`--cachedir`:** Where to cache downloaded packages

**`--dist`:** Build configuration file

**`--arch`:** Architecture compatibility list

**`--ccache`:** Compiler cache for faster rebuilds

**`--icecream`:** Distributed compilation

**`--baselibs`:** Create 32-bit compatibility packages

**`--extra-packs`:** Additional packages to install

**Lines 2254-2257: Per-package ccache**
- Some packages benefit more from ccache
- Config can enable per-package

---

### Lines 2261-2274: Repository Arguments
```perl
    my $count = scalar(keys %to_build) - scalar (@skipped);
    info("*** [$index/$count] building $name-$version-$release $arch $dist (worker: $thread) ***");

    if ( -d "$rpm_repo_path" ) {
        push @args, "--repository '$rpm_repo_path'";
    }
    
    foreach my $r (@package_repos) {
        push @args, "--repository $r";
    }
```

**Display progress:**
```
*** [3/15] building mypackage-1.0-1 x86_64 tizen (worker: 2) ***
```

**Repository order matters:**
1. Local repository first (highest priority)
2. Remote repositories next

**Why:** Prefer locally built packages over remote

---

### Lines 2276-2282: Clean Options
```perl
    if ( ($clean || $cleanonce ) && ( ! grep $_ == $thread, @cleaned) ) {
       push @args, "--clean";
       if ($cleanonce) {
            push(@cleaned, $thread);
       }
    }
```

**Clean Logic:**

**`--clean`:** Always clean
- Every build starts fresh
- Slower but more reliable

**`--clean-once`:** Clean first build only
- First build in thread: Add `--clean`
- Add thread to `@cleaned` list
- Subsequent builds: Reuse build root
- Faster for multiple packages

**Example with `--clean-once`:**
```
Thread 0, Build 1: --clean (first time)
Thread 0, Build 2: (reuse build root)
Thread 0, Build 3: (reuse build root)
```

---

### Lines 2283-2306: Build Root and VM Options
```perl
    my $scratch = "$scratch_dir.$thread";
    my $logpath= "$scratch/.build.log";
    
    if ($vmtype eq "kvm") {
        push @args, "--kvm";
        my $tmpdir_log = "$localrepo/$dist/$arch/logs/$name/";
        mkdir "$tmpdir_log", 0755;
        $logpath = "$tmpdir_log/.build.log";
        push @args, "--logfile $logpath";
    }
    
    if ($vmmemory ne "") {
        push @args, "--vm-memory=$vmmemory";
    }
    if ($vmswapsize ne "") {
        push @args, "--vm-swap-size=$vmswapsize";
    }
    if ($vmdisksize ne "") {
        push @args, "--vm-disk-size=$vmdisksize";
    }
    if ($vmdiskfilesystem ne "") {
        push @args, "--vm-disk-filesystem=$vmdiskfilesystem";
    }
    if ($vminitrd ne "") {
        push @args, "--vm-initrd=$vminitrd";
    }
    if ($vmkernel ne "") {
        push @args, "--vm-kernel=$vmkernel";
    }
```

**Build Root Path:**
```
~/GBS-ROOT/local/BUILD-ROOTS/scratch.x86_64.0
~/GBS-ROOT/local/BUILD-ROOTS/scratch.x86_64.1
...
~/GBS-ROOT/local/BUILD-ROOTS/scratch.x86_64.7
```

**Each thread has its own build root**

**VM Build Options:**
- More isolated than chroot
- Better security
- Slower startup
- Requires KVM support

---

### Lines 2308-2321: Additional Options
```perl
    if ($release_tag ne "") {
        push @args, "--release=$release_tag";
    }
    if ($nocumulate) {
        push @args, "--nocumulate";
    }
    
    my $redirect = "";
    if ($MAX_THREADS > 1 ) {
        $redirect = "> /dev/null 2>&1";
    }

    push @args, "--debug" if ($disable_debuginfo != 1);
    push @args, "--root '$scratch'";
    
    if ($noinit == 1 && -e "'$scratch'/not-ready") {
        error("build root is not ready , --noinit is not allowed");
    }
    push @args, "--clean" if (-e "'$scratch'/not-ready");
```

**`--release`:** Override Release tag in spec

**`--nocumulate`:** Don't accumulate build results

**Output redirection:**
- Single thread: Show all output
- Multiple threads: Suppress output (logs saved)
- Prevents mixed output from parallel builds

**`--debug`:** Create debuginfo packages

**`not-ready` file:** Indicates incomplete build root
- Created at start of init
- Removed when init completes
- If exists: Force clean

---

### Lines 2322-2327: Handle Incremental Build
```perl
    push @args, $redirect;
    for my $define (@defines) {
        push @args, "--define '$define'";
    }

    my $cmd = "";
    my $builddir;
```

**Custom macros:** From `--define` options

---

### Lines 2328-2393: Incremental Build Setup
```perl
    if ($not_ex) {
        my $base_source = get_source_base_name($to_build{$name}->{source});
        $builddir = "$scratch/home/abuild/rpmbuild/BUILD/$base_source";
    } else {
        $builddir = "$scratch/home/abuild/rpmbuild/BUILD/$name-$version";
    }
    
    my $source_tar = "";
    if (exists $to_build{$name}->{source}) {
        $source_tar = "$to_build{$name}->{project_base_path}/$packaging_dir/$to_build{$name}->{source}";
    }
    
    if ($incremental == 1) {
        info("doing incremental build");
        @args_inc = @args;
        my $buildcmd = "";
        
        if ( ! -d "$builddir" || grep($_ eq "--clean", @args_inc)){
            debug("Build directory does not exist");
            push @args_inc, "--no-build";
            push @args_inc, "--clean" if (! grep($_ eq "--clean", @args_inc));
            $cmd = join(" ", @args_inc);
            return -1 if (my_system($cmd) != 0);
        } else {
            debug("build directory exists");
        }

        # More incremental options
        if ($run_configure == 1 ) {
            push @args, "--define '%configure echo'";
            push @args, "--define '%reconfigure echo'";
            push @args, "--define '%autogen echo'";
        }
        
        push @args, "--root '$scratch'";
        push @args, "--no-topdir-cleanup";
        push @args, "--no-init";
        @args = grep { $_ ne "--clean"} @args;
        push @args, "--short-circuit --stage=\"-bs\"";

        my $project_base_path = $to_build{$name}->{project_base_path};
        if (! -e "$builddir") {
            my_system("sudo /bin/mkdir -p '$builddir'");
        }
        
        my $mount = "sudo /bin/mount -o bind '$project_base_path' '$builddir'";
        my_system($mount);
        
        my $tmp_dir = abs_path(tempdir(CLEANUP=>1));
        my_system("tar -zcf '$source_tar' '$tmp_dir'") if ("$source_tar" ne "");
    }
```

**Incremental Build Logic:**

**First Time (no build directory):**
1. Initialize build root
2. Don't actually build (`--no-build`)
3. Clean if needed

**Subsequent Times:**
1. Skip configure scripts (if `--no-configure`)
2. Mount source directory into build root
3. Build directly from mounted source
4. Create dummy source tarball

**Mount:**
```
Mount: /path/to/git/repo
  To:  /build-root/home/abuild/rpmbuild/BUILD/package-1.0
```

**Benefits:**
- Edit source files directly
- Rebuild instantly
- Debug build failures interactively

---

### Lines 2395-2419: No-Export Source Handling
```perl
    if ($not_ex) {
        if ( -d "$builddir") {
            my_system("rm -rf '$builddir'");
        }
        
        my $otherdir = "$scratch/home/abuild/rpmbuild/OTHER/";
        if ( ! -d "$otherdir") {
            my_system("sudo /bin/mkdir -p '$otherdir'");
        }
        
        my $project_base_path = $to_build{$name}->{project_base_path};
        my_system("sudo /bin/mkdir -p '$builddir'");
        
        my $mount = "sudo /bin/mount -o bind '$project_base_path' '$builddir'";
        my_system($mount);
        
        my $packaing_files = dirname($to_build{$name}->{filename});
        my_system("cp -a $packaing_files/* $project_base_path/");
        
        my $tmp_dir = abs_path(tempdir(CLEANUP=>1));
        my_system("tar -zcf $source_tar $tmp_dir") if ($source_tar ne "");
        
        push @args, "--short-circuit --stage=\"-bs\"";
        push @args, "--no-topdir-cleanup";
    } else {
        push @args, "--stage=\"-bb\"" if ($skip_srcrpm == 1);
    }
```

**No-Export Optimization:**
- Skip expensive `gbs export` step
- Mount source directly
- Copy packaging files to source
- Create dummy tarball
- Build in short-circuit mode

**Normal Mode:**
- Build binary packages only if skipping SRPM

---

### Lines 2421-2426: Execute Build
```perl
    $cmd = join(" ", @args);
    my $ret = my_system ($cmd);

    if ($incremental == 1) {
        my_system("rm -f '$source_tar'") if ($source_tar ne "");
        safe_umount($builddir) if ($incremental == 1);
    }
```

**Line 2421:** Join all arguments into command string

**Example Command:**
```bash
sudo /usr/bin/build \
  --uid 1000:1000 \
  --jobs 8 \
  --target x86_64 \
  --cachedir '/home/user/GBS-ROOT/local/cache' \
  --dist '/home/user/GBS-ROOT/meta/dist/tizen.conf' \
  --arch 'x86_64:i686:i586:i486:i386:noarch' \
  --repository '/home/user/GBS-ROOT/local/repos/tizen/x86_64/RPMS' \
  --repository 'http://download.tizen.org/releases/base/latest/repos/' \
  --clean \
  --root '/home/user/GBS-ROOT/local/BUILD-ROOTS/scratch.x86_64.0' \
  '/home/user/GBS-ROOT/local/sources/tizen/mypackage-1.0-1/mypackage.spec'
```

**Line 2422:** Execute command

**Lines 2424-2426: Incremental cleanup**
- Remove dummy tarball
- Unmount source directory
- Leave build directory intact for next build

---

### The safe_umount() Function

```perl
sub safe_umount {
    my ($device) = @_;
    
    return if (my_system("sudo /bin/umount -l '$device'") == 0);

    warning("!!!! umount device $device failed...");

    <>;
    
    if (my_system("sudo /bin/umount -l -f '$device'") != 0) {
        warning("!!!! IMPORTANT: umount failed again...");
    }
}
```

**Purpose:** Safely unmount with retry

**`-l` flag:** Lazy unmount
- Detach filesystem immediately
- Clean up when no longer busy

**`-f` flag:** Force unmount
- More aggressive
- Last resort

**Wait for user:** If first attempt fails
- Displays warning
- Waits for Enter key
- User can manually stop processes using mount

---

### Lines 2427-2433: Save Build Config for --noinit
```perl
    if ($not_ex) {
        my_system("rm -f '$source_tar'") if ($source_tar ne "");
        safe_umount($builddir)
    }

    my_system("sudo /bin/cp '$dist_configs/$dist.conf' '$scratch'/$dist.conf") if ($noinit == 0);
```

**Save config:** For future `--noinit` builds
- Copy `tizen.conf` to build root
- Build root remembers its distribution
- Later `--noinit` can read saved config

---

### Lines 2435-2482: Handle Build Success
```perl
    if ($ret == 0) {
        my $rpmdirpath;
        my $srcrpmdirpath;
        
        if ($vmtype eq "kvm") {
            $rpmdirpath = "/.build.packages/RPMS";
            $srcrpmdirpath = "/.build.packages/SRPMS";
        } else {
            $rpmdirpath = `sudo chroot '$scratch' su -c "rpm --eval %{_rpmdir} 2>/dev/null" - abuild`;
            $srcrpmdirpath = `sudo chroot '$scratch' su -c "rpm --eval %{_srcrpmdir} 2>/dev/null" - abuild`;
        }
        
        chomp($rpmdirpath);
        chomp($srcrpmdirpath);
        
        mkdir_p "$success_logs_path/$name-$version-$release";
        
        if (-e "$logpath") {
            my_system ("sudo /bin/mv '$logpath' '$success_logs_path'/$name-$version-$release/log.txt");
            
            if ($vmtype eq "kvm") {
                my $dir_logpath = dirname($logpath);
                my_system ("/bin/rm -rf '$dir_logpath'");
            }
            
            $succeeded{"$name"} = "$success_logs_path/$name-$version-$release/log.txt";
        }
```

**Build succeeded (`$ret == 0`):**

**Lines 2437-2446: Find RPM directories**
- KVM: Fixed paths in VM
- Chroot: Query RPM macros for paths
- Paths vary by distribution

**Example paths:**
```
RPMS:  /home/abuild/rpmbuild/RPMS
SRPMS: /home/abuild/rpmbuild/SRPMS
```

**Lines 2451-2461: Save build log**
- Move to success logs directory
- Organized by package name
- Store path in `%succeeded` hash

---

### Lines 2463-2483: Collect RPMs
```perl
        {
            lock($DETACHING);
            
            if (my @srpms = (`find "$scratch/$srcrpmdirpath" -type f -name "*.rpm" 2>/dev/null`)) {
                update_repo_with_rpms(\%srpmpaths, @srpms);
                
                if ($skip_srcrpm == 0){
                   foreach (@srpms) {
                       $_ =~ s/\n//; 
                       my_system ("sudo ln '$_' '$srpm_repo_path'");
                   }
                }
            } elsif ($skip_srcrpm == 1){
                my_system("/bin/rm -rf '$srpm_repo_path'/*.rpm");
            }
            
            if (my @rpms = (`find "$scratch/$rpmdirpath" -type f -name "*.rpm" 2>/dev/null`)) {
                update_repo_with_rpms (\%rpmpaths, @rpms);
                
                foreach (@rpms) {
                    $_ =~ s/\n//;
                    my_system ("sudo ln '$_' '$rpm_repo_path'");
                }
            }
        }
```

**Critical Section:** Protected by lock

**Source RPMs:**
1. Find all .src.rpm files
2. Remove old versions (`update_repo_with_rpms`)
3. Hard link to local repository
4. Hard link saves disk space (same inode)

**Binary RPMs:**
1. Find all .rpm files
2. Remove old versions
3. Hard link to local repository

**Result:** Local repository updated with new packages

---

### The update_repo_with_rpms() Function

```perl
sub update_repo_with_rpms {
    my ($ref_hash, @pkgs) = @_;
    
    foreach my $pkg (@pkgs) {
        my ($name, $version, $release, $arch) = get_pkg_info $pkg;
        next if $name eq '';
        
        my $na = "$name$arch";
        
        if (exists $ref_hash->{$na}) {
            foreach (@{$ref_hash->{$na}}) {
                my_system("rm -rf '$_'");
            }
        }
        
        $ref_hash->{$na} = [$pkg];
    }
}
```

**Purpose:** Remove old package versions

**Logic:**
1. Parse package name and architecture
2. Check if older version exists
3. Delete all old versions
4. Store new version in hash

**Example:**
```
Old: mylib-1.0-1.x86_64.rpm (delete)
New: mylib-1.0-2.x86_64.rpm (keep)
```

**Why:** Keep only latest version in repository

---

### Lines 2484-2488: Finish Success Handling
```perl
        info("finished building $name");
        $packages_built = 1;
        return 0;
```

**Set flag:** At least one package built
- Triggers repository metadata update
- Ensures `createrepo` runs

**Return 0:** Success status

---

### Lines 2489-2502: Handle Build Failure
```perl
    } else {
        mkdir_p "$fail_logs_path/$name-$version-$release";
        
        if ( -f "$logpath" ) {
            my_system ("sudo /bin/mv '$logpath' '$fail_logs_path'/$name-$version-$release/log.txt");
            
            if ($vmtype eq "kvm") {
                my $dir_logpath = dirname($logpath);
                my_system ("/bin/rm -rf '$dir_logpath'");
            }
            
            $errors{"$name"} = "$fail_logs_path/$name-$version-$release/log.txt";
            warning("build failed, Leaving the logs in $fail_logs_path/$name-$version-$release/log.txt");
        } else {
            $errors{"$name"} = "";
        }
        
        return 1;
    }
}
```

**Build failed (`$ret != 0`):**

**Save failure log:**
- Move to fail logs directory
- Store path in `%errors` hash
- Display warning message

**Return 1:** Failure status

---

## Post-Build Processing

### Lines 1533-1537: Wait for All Threads
```perl
while ((threads->list() > 0)) {
    sleep(1);
}
```

**Purpose:** Wait for all builds to complete

**`threads->list()`:** Returns count of running threads

**Blocks:** Until count reaches 0

---

### Lines 1539-1542: Final Repository Update
```perl
$work_done = 1;
update_repo();
my $build_status = build_report();
profiling_report();
```

**Line 1539:** Mark work complete
- Enables sub-package recalculation
- Final state

**Line 1540:** Update repository metadata

**Line 1541:** Generate build reports

**Line 1542:** Generate profiling reports (if enabled)

---

### The update_repo() Function

```perl
sub update_repo {
    if ($packages_built) {
        info("updating local repo");
        createrepo ($arch, $dist);
    }
    
    my @package_group_rpm = glob("$rpm_repo_path/package-groups-[0-9]*.rpm");
    my $tmp_dir = abs_path(tempdir(CLEANUP=>1));
    
    if ( @package_group_rpm != 0 and -e $package_group_rpm[0] ) {
        my_system("cd '$tmp_dir'; rpm2cpio $package_group_rpm[0] | cpio -di ");
        ( $patternfile ) = glob("$tmp_dir/*/*/*/patterns.xml");
    }
    
    if ( -e $patternfile ) {
        my_system("rm $localrepo/$dist/$arch/repodata/*patterns.xml.gz -f");
        my_system("modifyrepo $patternfile $localrepo/$dist/$arch/repodata >/dev/null");
    }
}
```

**Purpose:** Update repository metadata

**Lines 2508-2510: Run createrepo**
- Only if packages were built
- Regenerates all metadata

**Lines 2512-2520: Handle package groups**
- Package groups define software collections
- Example: "Base System", "Development Tools"
- Extracted from special `package-groups` RPM
- Added to repository metadata

---

### The createrepo() Function

```perl
sub createrepo {
    my $arch = shift;
    my $dist = shift;
    my $extra_opts = "--changelog-limit=0 -q";

    if ($skip_srcrpm == 0){
        my_system("touch '$srpm_repo_path'");
    }
    my_system("touch '$rpm_repo_path'");

    $extra_opts = $extra_opts . " --update " if ( -e "$localrepo/$dist/$arch/repodata" );
    $extra_opts = $extra_opts . " --groupfile=$groupfile " if ( -e "$groupfile");
    
    my_system ("createrepo $extra_opts '$localrepo/$dist/$arch' > /dev/null 2>&1 ") == 0 
        or die "createrepo failed: $?\n";
}
```

**Purpose:** Generate YUM/DNF repository metadata

**Options:**
- `--changelog-limit=0`: Don't include changelogs (faster)
- `-q`: Quiet mode
- `--update`: Update existing metadata (faster)
- `--groupfile`: Include package groups

**Output:** `repodata/` directory with XML files

---

## Build Report Generation

### The build_report() Function

```perl
sub build_report {
    my $msg = "*** Build Status Summary ***\n";

    my $total_packages = scalar(keys %to_build) - scalar (@skipped) + scalar (@export_errors);
    my $succeeded_packages = scalar(keys %succeeded);
    my $num_export_errors = scalar(@export_errors);
    my $num_expansion_errors = scalar(keys %expansion_errors);
    my $num_build_errors = scalar(keys %errors);
    
    my @export_details= ();
    my @expansion_details= ();
    my @build_details = ();
```

**Purpose:** Generate comprehensive build report

**Statistics:**
- Total packages attempted
- Successful builds
- Export errors
- Dependency errors
- Build errors

---

### Lines 2547-2561: Format Export Errors
```perl
    if (@export_errors) {
        $msg .= "=== the following packages failed to build because export " .
                "source files to build environment failed (" .
                scalar(@export_errors) . ") ===\n";
        
        foreach my $pkg (@export_errors) {
            $msg .= $pkg->{"package_name"} . "\n";
            
            push @export_details, {
                package_name => $pkg->{"package_name"},
                package_path => $pkg->{"package_path"},
                error_info => join("<br>", @{$pkg->{"error_info"}}),
            };
        }
        
        $msg .= "\n";
    }
```

**Export errors:** Failed during `gbs export`
- Git errors
- Missing tags/branches
- Spec file issues

---

### Lines 2562-2576: Format Expansion Errors
```perl
    if (%expansion_errors) {
        my $error_pkgs = "";
        
        foreach my $pkg (keys %expansion_errors) {
            $error_pkgs .= "$pkg:\n  " . join("\n  ", @{$expansion_errors{$pkg}}) . "\n";
            
            push @expansion_details, {
                package_name => $pkg,
                package_path => $to_build{$pkg}->{project_base_path},
                error_info => join("<br>", @{$expansion_errors{$pkg}}),
            };
        }
        
        $msg .= "=== the following packages failed to build due to missing " .
            "build dependencies (" . scalar(keys %expansion_errors) . ") ===\n$error_pkgs\n";
    }
```

**Expansion errors:** Unresolvable dependencies
- Missing packages
- Version conflicts
- Circular dependencies

**Example:**
```
mypackage:
  missing: libfoo-devel
  missing: libbar >= 2.0
```

---

### Lines 2577-2593: Format Build Errors
```perl
    if (%errors) {
        my $error_pkgs = "";
        
        foreach my $pkg (keys %errors) {
            $error_pkgs .= "$pkg: $errors{$pkg}\n";
            
            my $log =  $errors{$pkg};
            $log =~ s!\Q$localrepo/$dist/$arch/\E!!;
            
            push @build_details, {
                package_name => $pkg,
                package_path => $to_build{$pkg}->{project_base_path},
                succeeded => 0,
                log_path => $log,
            };
        }
        
        $msg .= "=== the following packages failed to build due to rpmbuild " .
            "issue (" . scalar(keys %errors) . ") ===\n$error_pkgs";
    }
```

**Build errors:** Failed during `rpmbuild`
- Compilation errors
- Missing files
- Spec file errors

**Log path:** Relative to local repo
- Example: `logs/fail/mypackage-1.0-1/log.txt`

---

### Lines 2595-2604: Format Success Details
```perl
    foreach my $pkg (keys %succeeded) {
        my $log =  $succeeded{$pkg};
        $log =~ s!\Q$localrepo/$dist/$arch/\E!!;
        
        push @build_details, {
            package_name => $pkg,
            package_path => $to_build{$pkg}->{project_base_path},
            succeeded => 1,
            log_path => $log,
        };
    }
    
    $msg .= "=== Total succeeded built packages: ($succeeded_packages) ===";
```

**Success details:** For HTML report

---

### Lines 2607-2622: Build JSON Structure
```perl
    $build_status_json{"build_profile"} = $dist;
    $build_status_json{"build_arch"} = $arch;
    $build_status_json{"build_start_time"} = $start_time;
    $build_status_json{"gbs_version"} = $gbs_version;
    $build_status_json{"summary"} = {
        packages_total => $total_packages,
        packages_succeeded => $succeeded_packages,
        packages_export_error  => $num_export_errors,
        packages_expansion_error => $num_expansion_errors,
        packages_build_error => $num_build_errors
    };
    
    $build_status_json{"export_details"} = \@export_details;
    $build_status_json{"expansion_details"} = \@expansion_details;
    $build_status_json{"build_details"} = \@build_details;
    $build_status_json{"html_report"} = "$localrepo/$dist/$arch/index.html";
    $build_status_json{"rpm_repo"} = "$rpm_repo_path";
```

**JSON structure:** Complete build information
- Summary statistics
- Detailed error information
- Paths to logs and RPMs

---

### Lines 2626-2631: Generate Reports
```perl
    build_html_report();
    build_json_report();

    info($msg);

    info("generated html format report:\n     $localrepo/$dist/$arch/index.html" );
    info("generated RPM packages can be found from local repo:\n     $rpm_repo_path");
```

**Outputs:**
1. HTML report (visual, browser-friendly)
2. JSON report (machine-readable)
3. Console summary

---

### The build_html_report() Function

```perl
sub build_html_report {
    my $template_file = "/usr/share/depanneur/build-report.tmpl";

    if (! -e $template_file) {
        warning("html template $template_file does not exist.");
        return;
    }

    my $tmpl = HTML::Template->new(filename => $template_file);
    
    $tmpl->param(
        build_profile => $build_status_json{"build_profile"},
        build_arch => $build_status_json{"build_arch"},
        build_start_time => $build_status_json{"build_start_time"},
        gbs_version => $build_status_json{"gbs_version"},
    );

    $tmpl->param($build_status_json{"summary"});

    if (@export_errors) {
        $tmpl->param(
            have_export_errors => 1,
            export_details => $build_status_json{"export_details"}
        );
    }

    if (%expansion_errors) {
        $tmpl->param(
            have_expansion_errors => 1,
            expansion_details => $build_status_json{"expansion_details"}
        );
    }

    $tmpl->param(
        build_details => $build_status_json{"build_details"}
    );

    open(my $report_html, '>', "$localrepo/$dist/$arch/index.html");
    $tmpl->output(print_to => $report_html);
    close($report_html);
}
```

**Purpose:** Generate HTML report from template

**Template variables:**
- Build metadata
- Summary counts
- Error details (if any)
- Build details (all packages)

**Output:** `~/GBS-ROOT/local/repos/tizen/x86_64/index.html`

---

### The build_json_report() Function

```perl
sub build_json_report {
    open(my $report_json, '>', "$localrepo/$dist/$arch/report.json");
    print $report_json to_json(\%build_status_json,{allow_nonref => 1});
    close($report_json);
}
```

**Purpose:** Generate JSON report

**Output:** `~/GBS-ROOT/local/repos/tizen/x86_64/report.json`

**Use Cases:**
- CI/CD integration
- Automated analysis
- Build dashboards

---

### Lines 2640-2647: Determine Exit Status
```perl
    info("build roots located in:\n     $scratch_dir.*");
    
    if (%errors || %expansion_errors || @export_errors || 
        ($succeeded_packages == 0 && @skipped == 0)) {
        return 1;
    }
    
    return 0;
}
```

**Exit with failure if:**
- Any build errors
- Any dependency errors
- Any export errors
- No packages built and none skipped

**Exit with success if:**
- All packages built successfully, OR
- All packages skipped (already built)

---

## Program Exit

### Lines 1543-1544: Exit
```perl
exit $build_status
```

**Exit codes:**
- `0`: Success (all packages built or skipped)
- `1`: Failure (errors occurred)

---

## Summary of Complete Execution Flow

### 1. Initialization Phase
- Parse command-line arguments
- Load configuration
- Setup paths and directories
- Configure architecture policies

### 2. Package Discovery Phase
- Search for git repositories
- Find spec files
- Read package metadata
- Store in `@pre_packs`

### 3. Source Preparation Phase
- Fork multiple processes
- Export source code in parallel using `gbs export`
- Cache exports for reuse
- Populate `@packs` with exported packages

### 4. Repository Metadata Phase
- Scan local RPM repository
- Download remote repository metadata
- Merge into `.repo.cache` file
- Parse into `%repo` hash

### 5. Package Parsing Phase
- Parse all spec files
- Extract name, version, dependencies, sub-packages
- Store in `%to_build` hash
- Map sub-packages to main packages

### 6. Dependency Resolution Phase
- Calculate direct dependencies
- Calculate reverse dependencies
- Expand to transitive closure
- Resolve skip list (already built)

### 7. Topological Sort Phase
- BFS algorithm to order packages
- Dependencies built before dependents
- Detect circular dependencies
- Store in `@build_order`

### 8. Worker Pool Setup Phase
- Initialize thread pool
- Setup signal handlers
- Check for mount points
- Scan existing RPMs

### 9. Main Build Loop Phase
- Find packages with satisfied dependencies
- Spawn threads for available workers
- Each thread calls `worker_thread()`
- Monitor for completion

### 10. Build Execution Phase (per thread)
- Construct build command
- Set build options
- Execute `sudo /usr/bin/build`
- Handle incremental/no-init modes

### 11. Result Handling Phase
- Move logs to success/fail directories
- Hard link RPMs to local repository
- Remove old package versions
- Update shared state

### 12. Post-Build Phase
- Wait for all threads
- Update repository metadata
- Generate build reports
- Exit with status

---

## Key Design Patterns

### Thread Safety
- **Shared variables:** `:shared` attribute
- **Critical sections:** `lock($DETACHING)` blocks
- **Atomic updates:** All state changes in locks

### Resource Management
- **Worker pool:** Fixed size, reusable threads
- **Build roots:** One per thread, isolated
- **Hard links:** Save disk space for RPMs

### Error Handling
- **Three error types:** Export, expansion, build
- **Graceful degradation:** Continue building other packages
- **Detailed logging:** Separate logs per package

### Performance Optimization
- **Parallel export:** Multiple packages simultaneously
- **Parallel build:** Up to N packages concurrently
- **Export cache:** Skip redundant exports
- **Incremental builds:** Mount source directly

### Dependency Management
- **Transitive closure:** Full dependency trees
- **Topological sort:** Correct build order
- **Circular detection:** Fail-fast on cycles
- **Dynamic updates:** Refresh after each build

---

## Complete Data Flow

```
Command Line
    ↓
Configuration Files
    ↓
Package Discovery (git repos)
    ↓
@pre_packs (package metadata)
    ↓
Parallel Source Export
    ↓
@packs (exported specs)
    ↓
Spec File Parsing
    ↓
%to_build (package info)
    ↓
Repository Metadata Retrieval
    ↓
%repo (all available packages)
    ↓
Dependency Resolution
    ↓
%pkgdeps, %pkgddeps (dependencies)
%pkgrdeps, %pkgrddeps (reverse deps)
    ↓
Topological Sort
    ↓
@build_order (build sequence)
    ↓
Main Build Loop
    ↓
Worker Threads (parallel builds)
    ↓
RPM Files in Local Repo
    ↓
Repository Metadata Update
    ↓
Build Reports (HTML + JSON)
    ↓
Exit Status
```

---

## Conclusion

The GBS build system is a sophisticated parallel build orchestrator that:

1. **Discovers** packages from git repositories
2. **Exports** source code efficiently with caching
3. **Resolves** complex dependency graphs
4. **Builds** multiple packages in parallel
5. **Manages** thread safety and resources
6. **Reports** comprehensive build results

It handles edge cases like circular dependencies, incremental builds, and build failures gracefully while maximizing build throughput through parallelization.

---

## End of Documentation

This completes the line-by-line documentation of the entire depanneur build system following the execution flow from start to finish.