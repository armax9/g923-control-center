// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <sys/file.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdexcept>
#include <string>
struct Ownership {
 int fd=-1;
 Ownership(){auto path=std::string("/tmp/g923-mac-bridge-")+std::to_string(getuid())+".lock";
 fd=open(path.c_str(),O_CREAT|O_RDWR|O_NOFOLLOW|O_CLOEXEC,0600);struct stat s{};
 if(fd<0||fstat(fd,&s)||s.st_uid!=getuid()||!S_ISREG(s.st_mode)||flock(fd,LOCK_EX|LOCK_NB)){if(fd>=0)close(fd);throw std::runtime_error("Another bridge/test owns output, or lock unavailable");}}
 ~Ownership(){if(fd>=0)close(fd);}
};
