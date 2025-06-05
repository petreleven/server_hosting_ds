let giftExample = new Promise((resolve, reject) => {
    setTimeout(() => {
        let wrapped = false;
        if (wrapped) {
            resolve("Your gift is ready");
        }
        else {
            reject("Not ready");
        }

    }, 3000)
})

/*
giftExample.then((result)=>{
    console.log(result);
}).catch((error)=>{
    console.log(error)
})
*/
async function run() {
    try {
        //handles resolve
        let result = await giftExample;
        console.log(result);
    } catch (error) {
        //handles reject
        console.log(error)
    }
}
run();

//RUNNING MULTIPLE ASYNC TASKS
function delay(seconds){
    new Promise((resolve, reject)=>{ setTimeout(resolve, 5000)})
}

function runSingle(tasknumber) {
    console.log("Starting ", tasknumber);

    console.log("Finished ", tasknumber);
}

async function startAllTasks() {
    await Promise.all([
        runSingle("Task1"),
        runSingle("Task2"),
        runSingle("Task3")])
}










