#!/bin/sh
# Sent to sh over SSH stdin. This script never creates remote files.
LC_ALL=C
LANG=C
export LC_ALL LANG
sm_interval=__SM_INTERVAL__
sm_disk_path=__SM_DISK_PATH__

trap 'exit 0' HUP INT TERM PIPE

if [ "$(uname -s 2>/dev/null)" != Linux ] || [ ! -r /proc/stat ] || [ ! -r /proc/meminfo ]; then
    printf '%s\n' 'Server Monitor: the remote host must be Linux with readable /proc/stat and /proc/meminfo.' >&2
    exit 1
fi
for sm_command in awk cat uname sleep; do
    if ! command -v "$sm_command" >/dev/null 2>&1; then
        printf 'Server Monitor: required remote command is missing: %s\n' "$sm_command" >&2
        exit 1
    fi
done

sm_facts=$(
    printf 'hostname\t%s\n' "$(uname -n)"
    printf 'kernel\t%s\n' "$(uname -r)"
    printf 'arch\t%s\n' "$(uname -m)"
    if [ -r /etc/os-release ]; then
        awk '{ print "os_release\t" $0 }' /etc/os-release
    elif [ -r /usr/lib/os-release ]; then
        awk '{ print "os_release\t" $0 }' /usr/lib/os-release
    fi
    if [ -r /proc/sys/kernel/random/boot_id ]; then
        printf 'boot_id\t%s\n' "$(cat /proc/sys/kernel/random/boot_id)"
    fi
    if [ -r /proc/cpuinfo ]; then
        awk -F: '
            function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
            {
                key = trim($1)
                value = $0
                sub(/^[^:]*:/, "", value)
                value = trim(value)
                if (model == "" && (key == "model name" || key == "Hardware" || key == "Processor")) model = value
                if (key == "cpu MHz" && value ~ /^[0-9]+([.][0-9]+)?$/) { mhz += value; count++ }
            }
            END {
                if (model != "") print "model\t" model
                if (count > 0) printf "mhz\t%.3f\n", mhz / count
            }
        ' /proc/cpuinfo
    fi
)

sm_have_timeout=0
if command -v timeout >/dev/null 2>&1; then
    sm_have_timeout=1
fi

# A minimal fallback for hosts without coreutils/BusyBox timeout. These are
# read-only, single-process commands; a watchdog prevents ordinary blocked
# queries from holding up CPU/RAM collection. The watchdog does not own the output
# pipe, and no temporary files or persistent remote processes are needed.
sm_run_fallback() (
    sm_limit=$1
    shift
    "$@" &
    sm_child_pid=$!
    (
        trap 'kill "$!" 2>/dev/null; wait "$!" 2>/dev/null; exit 0' HUP INT TERM
        sleep "$sm_limit" &
        wait "$!" || exit 0
        kill -KILL "$sm_child_pid" 2>/dev/null
    ) >/dev/null 2>&1 &
    sm_guard_pid=$!
    trap 'kill -KILL "$sm_child_pid" 2>/dev/null; kill "$sm_guard_pid" 2>/dev/null; wait "$sm_child_pid" 2>/dev/null; wait "$sm_guard_pid" 2>/dev/null; exit 124' HUP INT TERM
    wait "$sm_child_pid"
    sm_child_status=$?
    kill "$sm_guard_pid" 2>/dev/null
    wait "$sm_guard_pid" 2>/dev/null
    exit "$sm_child_status"
)

sm_run_bounded() {
    sm_seconds=$1
    shift
    command -v "$1" >/dev/null 2>&1 || return 127
    if [ "$sm_have_timeout" -eq 1 ]; then
        timeout -k 1 "$sm_seconds" "$@"
    else
        sm_run_fallback "$sm_seconds" "$@"
    fi
}

sm_disk_wait=0
sm_disk_lines=
sm_traffic_wait=0
sm_traffic_date=

while :; do
    if [ "$sm_disk_wait" -le 0 ]; then
        sm_disk_output=$(sm_run_bounded 3 df -Pk "$sm_disk_path")
        sm_disk_status=$?
        if [ "$sm_disk_status" -eq 0 ]; then
            sm_disk_lines=$(printf '%s\n' "$sm_disk_output" | awk 'NR > 1 { print "df\t" $0 }')
        else
            sm_disk_lines=
            printf 'Server Monitor: disk data unavailable for %s (df exit %s); other metrics continue.\n' "$sm_disk_path" "$sm_disk_status" >&2
        fi
        sm_disk_wait=10
    fi

    # GNU ps reports lifetime-average CPU (possibly >100%) and RSS in KiB.
    # Publish names only; arguments and usernames never cross the wire.
    sm_process_lines=$(
        (sm_run_bounded 2 ps -eo pid=,pcpu=,rss=,comm= --sort=-pcpu 2>/dev/null && printf '%s\n' '__SM_OK__') |
        awk '
            $0 == "__SM_OK__" { ok = 1; next }
            NF >= 4 {
                pid = $1; cpu = $2; rss = $3
                sub(/^[ \t]*[^ \t]+[ \t]+[^ \t]+[ \t]+[^ \t]+[ \t]+/, "")
                gsub(/[[:cntrl:]]/, "?")
                line = "process\t" pid "\t" cpu "\t" rss "\t" substr($0, 1, 128) "\n"
                if (NR <= 5) { lines = lines line; emitted[pid] = 1 }
                for (i = 1; i <= 5; i++) {
                    if (!(i in memory) || rss + 0 > memory[i]) {
                        for (j = 5; j > i; j--) { memory[j] = memory[j-1]; rows[j] = rows[j-1]; ids[j] = ids[j-1] }
                        memory[i] = rss + 0; rows[i] = line; ids[i] = pid
                        break
                    }
                }
            }
            END {
                if (ok) {
                    printf "processes_available\t1\n%s", lines
                    for (i = 1; i <= 5; i++) if (i in rows && !(ids[i] in emitted)) printf "%s", rows[i]
                }
            }
        '
    )

    # Only query an existing vnStat database, never initialize or update it.
    # Retry at most once/minute, and immediately when the server day changes.
    sm_today=$(date '+%Y-%m-%d' 2>/dev/null)
    if [ "$sm_today" != "$sm_traffic_date" ]; then sm_traffic_wait=0; fi
    sm_traffic_refresh=0
    sm_traffic_lines=
    if [ "$sm_traffic_wait" -le 0 ]; then
        sm_traffic_refresh=1
        sm_traffic_date=$sm_today
        if command -v vnstat >/dev/null 2>&1; then
            sm_traffic_lines=$(
                (sm_run_bounded 3 vnstat --json d 7 2>/dev/null && printf '\n%s\n' '__SM_OK__') |
                awk '
                    $0 == "__SM_OK__" { ok = 1; next }
                    { size += length($0) + 1; if (size <= 49152) data = data $0; else large = 1 }
                    END { if (ok && !large && data != "") print "vnstat\t" data }
                '
            )
        fi
        sm_default_interface=
        if [ -r /proc/net/route ]; then
            sm_default_interface=$(awk '$2 == "00000000" && $7 ~ /^[0-9]+$/ { if (!found || $7 + 0 < metric) { name = $1; metric = $7 + 0; found = 1 } } END { print name }' /proc/net/route)
        fi
        if [ -z "$sm_default_interface" ] && [ -r /proc/net/ipv6_route ]; then
            sm_default_interface=$(awk '$1 == "00000000000000000000000000000000" && $2 == "00" { print $10; exit }' /proc/net/ipv6_route)
        fi
        sm_traffic_wait=60
    fi

    sm_temperature=$(sm_run_bounded 1 vcgencmd measure_temp 2>/dev/null) || sm_temperature=

    printf '%s\n' '__SM_BEGIN__' 'version	1' || exit 0
    printf '%s\n' "$sm_facts" || exit 0
    if [ -n "$sm_temperature" ]; then
        printf '%s\n' "$sm_temperature" | awk '/^temp=[0-9]+([.][0-9]+)?\047C$/ {
            sub(/^temp=/, ""); sub(/\047C$/, ""); print "temperature_c\t" $0
        }'
    fi
    printf 'disk_path\t%s\n' "$sm_disk_path"
    if [ -n "$sm_disk_lines" ]; then
        printf '%s\n' "$sm_disk_lines"
    fi
    if [ -n "$sm_process_lines" ]; then printf '%s\n' "$sm_process_lines"; fi
    if [ "$sm_traffic_refresh" -eq 1 ]; then
        printf 'traffic_refresh\t1\ntraffic_date\t%s\ndefault_interface\t%s\n' "$sm_traffic_date" "$sm_default_interface"
        if [ -n "$sm_traffic_lines" ]; then printf '%s\n' "$sm_traffic_lines"; fi
    fi
    awk '
        /^cpu / {
            printf "cpu"
            for (i = 2; i <= NF; i++) printf "\t%s", $i
            printf "\n"
        }
        /^cpu[0-9]+ / { cores++ }
        /^btime / { print "btime\t" $2 }
        END { if (cores > 0) print "cores\t" cores }
    ' /proc/stat
    awk '{ print "meminfo\t" $0 }' /proc/meminfo
    if [ -r /proc/uptime ]; then
        awk '{ print "uptime\t" $1 }' /proc/uptime
    fi
    if [ -r /proc/loadavg ]; then
        awk '{ print "load\t" $1 "\t" $2 "\t" $3 }' /proc/loadavg
    fi
    printf '%s\n' '__SM_END__' || exit 0
    sm_disk_wait=$((sm_disk_wait - sm_interval))
    sm_traffic_wait=$((sm_traffic_wait - sm_interval))
    sleep "$sm_interval" || exit 0
done
