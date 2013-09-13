%global rvm_dir /usr/lib/rvm
%global rvm_group rvm

# RVM can not be sourced with default /bin/sh
%define _buildshell /bin/bash

# PL conventions
%define name rvm-ruby
# pick a RVM version from https://github.com/wayneeseguin/rvm/tags
%define version 1.22.9
%define taglevel 0
%define release %{taglevel}%{?pldistro:.%{pldistro}}%{?date:.%{date}}

Summary: Ruby Version Manager (including Rubies and Gems)
Name: %{name}
Version: %{version}
Release: %{release}
License: ASL 2.0
URL: http://rvm.io/
Group: Applications/System
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-%(%{__id_u} -n)

BuildRequires: bash curl git
BuildRequires: gcc-c++ patch chrpath readline readline-devel zlib-devel libyaml-devel libffi-devel openssl-devel autoconf automake libtool bison
BuildRequires: sed grep tar gzip bzip2 make file
# for OMF:
BuildRequires: tar libxml2 libxml2-devel libxslt libxslt-devel

Requires(pre): shadow-utils
# For rvm
Requires: bash curl git
# Basics for building ruby 1.8/1.9
# We expect all the building to take place .. at build-time, so let's take this out
#Requires: gcc-c++ patch readline readline-devel zlib-devel libyaml-devel libffi-devel openssl-devel autoconf automake libtool bison
# Used by the scripts
Requires: sed grep tar gzip bzip2 make file
# for OMF:
Requires: libxml2 libxslt

%description
RVM is the Ruby Version Manager. It manages Ruby interpreter environments
and switching between them.

This package is meant for use by multiple users maintaining a shared copy of
RVM. Users added to the '%{rvm_group}' group will be able to modify all aspects
of RVM. These users will also have their default umask modified ("g+w") to allow
group write permission (usually resulting in a umask of "0002") in order to
ensure correct permissions for the shared RVM content.

RVM is activated for all logins by default. To disable remove
%{_sysconfdir}/profile.d/rvm.sh and source rvm from each users shell.

%install
rm -rf %{buildroot}

# Clean the env
for i in $(env | grep ^rvm_ | cut -d"=" -f1); do
  unset $i;
done

# Install everything into one directory
(
export rvm_ignore_rvmrc=1 \
  rvm_user_install_flag=0 \
  rvm_path="%{buildroot}%{rvm_dir}" \
  rvm_man_path="%{buildroot}%{_mandir}" \
  HOME=%{buildroot}
\curl -L https://get.rvm.io | bash -s stable --version %{version}
)

# So members of the rvm group can write to it
find %{buildroot}%{rvm_dir} -exec chmod ug+w {} \;
find %{buildroot}%{rvm_dir} -type d -exec chmod g+s {} \;

mkdir -p %{buildroot}%{_sysconfdir}

# We use selfcontained so binaries end up in rvm/bin
cat > %{buildroot}%{_sysconfdir}/rvmrc <<END_OF_RVMRC
# Setup default configuration for rvm.
# If an rvm install exists in the home directory, don't load this.'
if [[ ! -s "\${HOME}/.rvm/scripts/rvm" ]]; then

  # Only users in the rvm group need the umask modification
  for i in \$(id -G -n); do
    if [ \$i = "rvm" ]; then
      umask g+w
      break
    fi
  done

  export rvm_user_install_flag=1
  export rvm_path="%{rvm_dir}"
fi
END_OF_RVMRC

mkdir -p %{buildroot}%{_sysconfdir}/profile.d

cat > %{buildroot}%{_sysconfdir}/profile.d/rvm.sh <<END_OF_RVMSH
# rvm loading hook
#
if [ -s "\${HOME}/.rvm/scripts/rvm" ]; then
  source "\${HOME}/.rvm/scripts/rvm"
elif [ -s "%{rvm_dir}/scripts/rvm" ]; then
  source "%{rvm_dir}/scripts/rvm"
fi
END_OF_RVMSH

chmod 755 %{buildroot}%{_sysconfdir}/profile.d/rvm.sh

# At this point, install of RVM is finished
# Now install some rubies

# Run this in a subshell so the rvm loading does not infect our current shell.
(
export rvm_ignore_rvmrc=1
export rvm_user_install_flag=0
export rvm_path="%{buildroot}%{rvm_dir}"
export rvm_man_path="%{buildroot}%{_mandir}"
source ${rvm_path}/scripts/rvm
gemi='gem install --no-ri --no-rdoc'

ruby_tag=ruby-1.9.3-p286
rvm install $ruby_tag --verify-downloads 1
rvm use $ruby_tag
rvm gemset create omf
rvm use $ruby_tag@omf --default
$gemi omf_rc
#$gemi whatever_gem_you_need

#ruby_tag=ruby-1.8.7-p352
#rvm install $ruby_tag
#rvm use $ruby_tag
rvm cleanup all
)

export br=%{buildroot}

# Strip binaries
#find $br -type f -print0 |xargs -0 file --no-dereference --no-pad |grep 'not stripped' |cut -f1 -d: |xargs -r strip

# Strip and Fix bad paths in generated files
# That is not optimized, but that is not supposed to be done often
for f in $(find $br -type f -print0 |xargs -0 file --no-dereference --no-pad |grep ': ELF' |cut -f1 -d:); do
  strip $f
  grep "$br" $f || continue
  line=$(chrpath -l $f) || continue
  echo $line |grep "$br" || continue
  chrpath -r $(echo $line |cut -f2 -d= |sed "s,$br,,") $f
done

# Replace bad paths in text files
find $br -type f \( -name \*.log -o -name \*.la \) -print0 |xargs -0 -r sed -i "s,$br,,g"
find $br -type f -print0 |xargs -0 file --no-dereference --no-pad |grep ': .* text' |cut -f1 -d: |xargs -r sed -i "s,$br,,g"

# Replace bad paths in all remaining files
# Padding with zeroes broke the LOAD_PATH in libruby, therefore prepend path with harmless forward slashes
printf -vch "%${#br}s" ""
slashes=$(printf "%s" "${ch// //}")
find $br -type f -print0 | xargs -0 sed -i "s,$br,$slashes,g"

# Fix symlinks with bad path
# the canonical path of the build root
brc=$(readlink -f $br)
for f in $(find $br -type l); do
    # some symlinks are relative, in which case we want to preserve them
    # do *not* mention -f here as it would always return an absolute path
    dest=$(readlink $f)
    # relative symlinks have $dest not starting with a /
    first_step=$(echo $dest | cut -d / -f1)
    # absolute paths have a void first_step 
    if [ -z "$first_step" ] ; then
	# destination is an absolute path, let's fix it
	# call readlink with -f so all symlinmks are solved
	# and so we can reliably substitute $brc that is also canonicalized
	destc=$(readlink -f $f | sed -e "s,^$brc,,")
	ln -sfn $destc $f
    fi
done

find $br -maxdepth 1 -name '.*' -exec rm -rf {} \;
rm $br/usr/share/man/man1/rvm.1.gz

%clean
rm -rf %{buildroot}
# it appears that, because we build as root, rvm installs stuff in /etc on the build box
# which is not desirable, so let us get rid of that - don't worry if that fails
find /etc -name 'rvm*' | xargs rm || :

%pre
getent group %{rvm_group} >/dev/null || groupadd -r %{rvm_group}
exit 0

%files
%defattr(-,root,root)
%config(noreplace) /etc/rvmrc
%config(noreplace) /etc/profile.d/rvm.sh
%attr(-,root,%{rvm_group}) %{rvm_dir}
%{_mandir}/man1/*

%changelog
* Sun Jul 14 2013 Thierry Parmentelat - rvm-ruby-1.20.10-8
- create an omf gemset (in rvm-ruby-1.20.10-7)
- make omf the default gemset
- add libxml2 and lixslt dependencies for omf

* Tue Jun 25 2013 Thierry Parmentelat - rvm-ruby-1.20.10-6
- add omf-rc in the mix

* Fri May 18 2013 Christoph Dwertmann - 4.xxx
- downloads RVM instead of relying on local sources
- works with latest RVM and Fedora
- removed ruby build dependency
- no more clashing with distribution ruby

* Fri Mar 30 2012 Alexandre Fouche - 3.xxx
Add some rubies and gems to compile:
- 1.9.2-p290 + bundler, bluepill, whenever
- 1.9.3-p0 + bundler, bluepill, whenever

* Thu Mar 29 2012 Alexandre Fouche - 2.xxx
- Adapt <https://github.com/mdkent/rvm-rpm/blob/master/SPECS/rvm-ruby.spec> to make it work from RVM git source directly
- Strip binaries, libraries, ...

* Thu Mar 29 2012 Alexandre Fouche - 1.xxx
- Adapt <https://github.com/mdkent/rvm-rpm/blob/master/SPECS/rvm-ruby.spec> to make it work from RVM git source directly

* Tue Dec 13 2011 Matthew Kent <mkent@magoazul.com> - 1.10.0-2
- New upstream release
- Drop rvm_prefix
- Rename rvm_user_install to rvm_user_install_flag
- Rename rake wrapper to rvm-rake
- Add file dependency

* Thu Aug 4 2011 Matthew Kent <mkent@magoazul.com> - 1.6.32-1
- New upstream release

* Tue Apr 19 2011 Matthew Kent <mkent@magoazul.com> - 1.6.3-1
- Initial package based off Gentoo work
