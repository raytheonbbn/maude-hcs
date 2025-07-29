# MAUDE_HCS: maude_hcs
# Software Markings (UNCLASS)
# PWNDD Software
# Copyright (C) 2025 RTX BBN Technologies Inc. All Rights Reserved
# Contract No: HR00112590083
# Contractor Name: RTX BBN Technologies Inc.
# Contractor Address: 10 Moulton Street, Cambridge, Massachusetts 02138
# 
# The U.S. Government's rights to use, modify, reproduce, release, perform, 
# display, or disclose these technical data and software are defined in the 
# Article VII: Data Rights clause of the OTA.
# 
# This document does not contain technology or technical data controlled under 
# either the U.S. International Traffic in Arms Regulations or the U.S. Export 
# Administration Regulations.
# 
# DISTRIBUTION STATEMENT A: Approved for public release; distribution is 
# unlimited.
# 
# Notice: Markings. Any reproduction of this computer software, computer 
# software documentation, or portions thereof must also reproduce the markings 
# contained herein.
# MAUDE_HCS: end


PROJECT=maude_hcs

PROJECT_DIR=$PWD

make_manifest() {

    local MANIFEST=$PROJECT_DIR/manifest.txt

    # check that what we're building is reflected in the git repo...
    #
    (cd $PROJECT_DIR; git diff-index --quiet HEAD --)
    if [ $? -ne 0 ]; then
        echo "WARNING: there are uncommitted changes on this branch!"
    fi

    rm -f "$MANIFEST"
    echo Built by $USER@$HOSTNAME > "$MANIFEST"
    (cd $PROJECT_DIR; git log -n 1 | head -1) >> "$MANIFEST"
    (cd $PROJECT_DIR; git branch | grep "^*" | awk '{print $2}') >> "$MANIFEST"
}

make_relname() {

    # we're just going to use timestamps (in the local time zone)
    # for the release name right now.  Eventually we might want
    # git branches/hashcodes/tags or some other way of naming things.

    echo $(date +"$PROJECT-%Y%m%d-%H%M")
}


make_tarball() {
    local RELNAME=$(make_relname)
    local TARBALL="$PROJECT_DIR/$RELNAME".tar
    local TGZBALL="$PROJECT_DIR/$RELNAME".tgz

    (cd $PROJECT_DIR &&
            tar cf "$TARBALL" \
                    use-cases \
                    results/examplar_corporate_prob.maude \
                    results/latency.quatex \
                    results/smc.maude \
                    DEVELOPER.md \
                    docs \
                    HCSParamsGuide.md \
                    NOTES.md \
                    pyproject.toml \
                    README.md \
                    runexp.sh \
                    maude_hcs.egg-info \
                    maude_hcs/*.py \
                    maude_hcs/cli/*.py \
                    maude_hcs/deps/dns_formalization \
                    maude_hcs/lib/common/*.py \
                    maude_hcs/lib/dns/*.py \
                    maude_hcs/lib/dns/README.md \
                    maude_hcs/lib/dns/maude/common \
                    maude_hcs/lib/dns/maude/nondet \
                    maude_hcs/lib/dns/maude/probabilistic \
                    maude_hcs/lib/dns/maude/smc \
                    maude_hcs/parsers/*.py \
                    manifest.txt)
    if [ $? -ne 0 ]; then
        echo "ERROR: make_tarball failed"
        rm -f "$TARBALL"
        exit 1
    fi

    # Make sure there's an empty log directory that is owned by $USER
    # (not root) and chmod it to try to make it possible for all the
    # subprocesses to access and create files within.  This can still
    # go wrong if untar'd as root.
    #
#    (mkdir -p log-$$/log && cd log-$$ && chmod 777 log)
#    if [ $? -ne 0 ]; then
#        echo "ERROR: could not create empty log directory"
#        exit 1
#    fi
#    (cd log-$$ && tar rf "$TARBALL" log)
#    if [ $? -ne 0 ]; then
#        echo "ERROR: could not add log directory to tarball"
#        exit 1
#    fi
#    rm -rf log-$$

    gzip -c "$TARBALL" > "$TGZBALL"
    if [ $? -ne 0 ]; then
        echo "ERROR: could not gzip $TARBALL"
        rm -f "$TARBALL" "$TGZBALL"
        exit 1
    fi

    rm -f "$TARBALL"
}

make_manifest

make_tarball
echo Created $(make_relname).tgz



