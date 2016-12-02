cdist-ng - Your system management swiss army knife
==================================================

cdist next generation is a complete rewrite of the cdist_ configuration management tool.
It was created for the following three reasons:

1) I was increasingly unhappy with the structure and implementation of cdist_. It had grown into something that I did not enjoy working on anymore.
2) I felt that cdist was sometimes slow.
3) I wanted to experiment with Python 3's new asyncio feature with a non-trivial codebase.


cdist_ vs cdist-ng_
-------------------

The manifests and types are currently mostly compatible.
cdist-ng_ can use all or most existing types from cdist_.

Some features have not yet been implemented.
And some where dropped because either the idea or the implementation sucked.


Definitions
-----------

session
   Represent a single cdist invocation which operates on one or more targets.
   A session_ is shared among all targets.

target
   The information related to a single target_.
   Each target has it's own instance.

runtime
   Implements the core functionality for interacting with a target.
   Each target_ has it's own instance of the runtime_.

transport
   transport_ protocols are used to interact with a target.
   This is similar to what remote exec/copy scripts where in cdist_.
   The difference is that they can be stacked. e.g. ssh+sudo+chroot.


Top level overview
------------------

The core of cdist-ng_ is implemented as a runtime engine or kernel.
During execution all state is held in memory as dictionaries.
cconfig_ is used to read/write state to disk when interacting with shell scripts.

When cdist-ng_ is run it creates a session_.
The session holds all the configuration and state required to interact with one or more target_'s.

Targets are passed to cdist-ng_ as uri's.
For each given target uri cdist-ng_ creates a target_ instance that holds the configuration and state to interact with a target.
Then for each target a runtime_ instance is created.
The runtime_ instance is then used perform the actual work on the target.

An example of all this in action can be seen in the `config subcommand`_


Current state
-------------
Most things are working.
I can configure my hosts using cdist-ng_ using the same manifests as when using legacy cdist_.
Beware that the CDIST_ORDER_DEPENDENCY feature is currently not implemented.


Installation
------------

.. code-block:: shell

   # grab the source
   mkdir ~/src
   git clone https://github.com/asteven/cdist-ng.git ~/src/cdist-ng
   # create and enter virtualenv
   mkvirtualenv --python=/usr/bin/python3 cdist-ng
   workon cdist-ng

   # editable install
   cd ~/src/cdist-ng
   pip install -e requirements.txt

   # run
   cdng --help
   # run with example manifest from ./conf/manifest/init
   cdng -v config localhost
   # which is the same as
   cdng -v config ssh://localhost


.. _session: cdist/session.py
.. _target: cdist/target.py
.. _runtime: cdist/runtime.py
.. _transport: conf/transport/
.. _config subcommand: cdist/cli/commands/config.py
.. _runtime system: http://en.wikipedia.org/wiki/Runtime_system
.. _cdist: https://github.com/ungleich/cdist/
.. _cdist-ng: https://github.com/asteven/cdist-ng/
.. _cconfig: https://github.com/asteven/cconfig/

