TODO LIST
=========

General things that need doing:

  * Set up unit testing and write some tests!
  * Write some more documentation including man pages
  * `nrpe_ng.config`: `include_dir` should recurse

For the server only:

  * Address-bases ACLs (`allowed_hosts`)
  * Command prefixing (`command_prefix`)
  * Command run-time timeout (`command_timeout`)
  * Networking timeout (`connection_timeout`)

For the client only:

  * SSL server verification on/off (`ssl_verify_server`)
  * Execution timeout (`--timeout`)
  * Option to return UNKNOWN on timeout rather than CRITICAL (`-u`)

# vi:ft=markdown
