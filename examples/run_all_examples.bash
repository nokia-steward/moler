EXAMPLES_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
MOLER_REPO_DIR="$( cd $EXAMPLES_DIR/.. >/dev/null && pwd )"

exit_status=0

for file in `find $EXAMPLES_DIR -name "*.py" -print`
do
    echo "**********************************************************************************"
    echo "*"
    echo "*  RUNNING: $file"
    echo "*"
    echo "**********************************************************************************"

    export PYTHONPATH=$MOLER_REPO_DIR:$PYTHONPATH
    python3 $file
    single_example_exit_status=$?

    if [ $single_example_exit_status != 0 ]
    then exit_status=$single_example_exit_status
    fi
    echo
done
exit $exit_status
