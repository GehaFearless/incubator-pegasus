/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

#pragma once

#include <string>

#include <dsn/utility/singleton.h>

class global_env : public dsn::utils::singleton<global_env>
{
public:
    std::string _pegasus_root;
    std::string _working_dir;
    std::string _host_ip;

private:
    global_env();
    global_env(const global_env &other) = delete;
    global_env(global_env &&other) = delete;
    ~global_env() = default;

    void get_hostip();
    void get_dirs();

    friend dsn::utils::singleton<global_env>;
};
