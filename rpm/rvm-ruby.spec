%global rvm_dir /usr/lib/rvm
%global rvm_group rvm

# RVM can not be sourced with default /bin/sh
%define _buildshell /bin/bash

Name: rvm-ruby
Summary: Ruby Version Manager
Version: 3  # Version will be appended the commit date
Release: 1.20.9
License: ASL 2.0
URL: http://rvm.beginrescueend.com/
Group: Applications/System

#BuildArch: noarch
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-%(%{__id_u} -n)

BuildRequires: bash curl git
BuildRequires: gcc-c++ patch chrpath readline readline-devel zlib-devel libyaml-devel libffi-devel openssl-devel
BuildRequires: sed grep tar gzip bzip2 make file

Requires(pre): shadow-utils
# For rvm
Requires: bash curl git
# Basics for building ruby 1.8/1.9
#Requires: gcc-c++ patch readline readline-devel zlib-devel libyaml-devel libffi-devel openssl-devel
# Used by the scripts
Requires: sed grep tar gzip bzip2 make file

%description
RVM is the Ruby Version Manager (rvm). It manages Ruby interpreter environments
and switching between them.

This package is meant for use by multiple users maintaining a shared copy of
RVM. Users added to the '%{rvm_group}' group will be able to modify all aspects
of RVM. These users will also have their default umask modified ("g+w") to allow
group write permission (usually resulting in a umask of "0002") in order to
ensure correct permissions for the shared RVM content.

RVM is activated for all logins by default. To disable remove
%{_sysconfdir}/profile.d/rvm.sh and source rvm from each users shell.

%prep
%setup -q

%build

%install
rm -rf %{buildroot}

# Clean the env
for i in `env | grep ^rvm_ | cut -d"=" -f1`; do
  unset $i;
done

# Install everything into one directory
export rvm_ignore_rvmrc=1 \
  rvm_user_install_flag=0 \
  rvm_path="%{buildroot}%{rvm_dir}" \
  rvm_bin_path="%{buildroot}%{_bindir}" \
  rvm_man_path="%{buildroot}%{_mandir}" \
  HOME=%{buildroot}

\curl -L https://get.rvm.io | bash -s stable --version %{release}
  #./install

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

#mv %{buildroot}%{_bindir}/rake %{buildroot}%{_bindir}/rvm-rake


# At this point, install of RVM is finished
# Now install some rubies

# Run this in a subshell so the rvm loading does not infect our current shell.
(
export rvm_ignore_rvmrc=1
export rvm_user_install_flag=0
export rvm_path="%{buildroot}%{rvm_dir}"
export rvm_bin_path="%{buildroot}%{_bindir}"
export rvm_man_path="%{buildroot}%{_mandir}"
source ${rvm_path}/scripts/rvm
gemi='gem install --no-ri --no-rdoc'

#touch $rvm_path/RELEASE
ruby_tag=ruby-1.9.3-p286
rvm install $ruby_tag
rvm use $ruby_tag
#$gemi bundler

#ruby_tag=ruby-1.8.7-p352
#rvm install $ruby_tag
#rvm use $ruby_tag
)

export br=%{buildroot}

# Remove sources
rm -rf $br/usr/lib/rvm/src

# Strip binaries
#find $br -type f -print0 |xargs -0 file --no-dereference --no-pad |grep 'not stripped' |cut -f1 -d: |xargs -r strip

# Strip and Fix bad paths in generated files
# That is not optimized, but that is not supposed to be done often
for f in `find $br -type f -print0 |xargs -0 file --no-dereference --no-pad |grep ': ELF' |cut -f1 -d:`; do
  strip $f
  grep "$br" $f || continue
  line=`chrpath -l $f` || continue
  echo $line |grep "$br" || continue
  chrpath -r `echo $line |cut -f2 -d= |sed "s,$br,,"` $f
done

# Replace bad paths in text files
find $br -type f \( -name \*.log -o -name \*.la \) -print0 |xargs -0 -r sed -i "s,$br,,g"
find $br -type f -print0 |xargs -0 file --no-dereference --no-pad |grep ': .* text' |cut -f1 -d: |xargs -r sed -i "s,$br,,g"

# Strip object files in ar archives from bad path strings
for f in `find $br -type f -name \*.a`; do
  td=`mktemp -d`
  pushd $td
  ar x $f

  for g in `find . -type f -print0 |xargs -0 file --no-dereference --no-pad |grep ': ELF' |cut -f1 -d:`; do
    strip $g
    grep "$br" $g || continue

    # Replace the bad path with the good one, padded by nulls
    ruby -p -i -e '
      $_.encode!("UTF-8", "UTF-8", :invalid => :replace).gsub!(/#{ENV["br"]}(.*?)\0/) do |s|
      $1 + ( "\0" * ENV["br"].size ) + "\0"
      end
    ' $g
  done

  ar r $f *
  popd
  rm -rf $td
done

# Replace paths in libraries strings
for f in `find $br/usr/lib/rvm/rubies -type f -print0 |xargs -0 file --no-dereference --no-pad |grep ': ELF' |cut -f1 -d:`; do
  grep "$br" $f || continue

  # Replace the bad path with the good one, padded by nulls
  ruby -p -i -e '
    $_.encode!("UTF-8", "UTF-8", :invalid => :replace).gsub!(/#{ENV["br"]}(.*?)\0/) do |s|
    $1 + ( "\0" * ENV["br"].size ) + "\0"
    end
  ' $f
done

# Fix symlinks with bad path
for f in `find $br -type l |grep "$br"`; do
    ln -sfn `readlink -f $f |sed "s,$br,,"` $f
done

find $br -maxdepth 1 -name '.*' -exec rm -rf {} \;

%clean
rm -rf %{buildroot}

%pre
getent group %{rvm_group} >/dev/null || groupadd -r %{rvm_group}
exit 0

%files
%defattr(-,root,root)
%config(noreplace) /etc/rvmrc
%config(noreplace) /etc/profile.d/rvm.sh
%attr(-,root,%{rvm_group}) %{rvm_dir}
%{_bindir}/*
%{_mandir}/man1/*

%changelog
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
