# Domino CDK to Terraform migration

Domino is deprecating this CDK repository, and switching all future EKS
provisioning work to our Terraform module, located here:

https://github.com/dominodatalab/terraform-aws-eks

The scripts in this directory will help you convert the management your
CDK-provisioned Domino infrastructure to the above Terraform module.

Your EKS cluster, EFS store, and S3 buckets will all remain in-tact.
The original ASGs and any bastion used for the install will be replaced
by ones generated in Terraform.

## Contents

* convert.py - The core migration script
* README.md - This file
* cdk_tf/ - Terraform to take over CDK infrastructure that will not be imported onto the terraform-aws-eks module.
* cloudformation-only/ - Terraform to create a special IAM role to remove the CDK CloudFormation stack

## Migration steps

To convert the CDK stack to terraform, we will...

1. Generate the terraform modules structure.
2. Generate input variables into Terraform
3. Generate import blocks into Terraform
4. Initialize the Terraform directory.
5. Evaluate the Terraform plans.
6. Apply the Terraform plans.
7. Scale down the old auto-scaling groups.
8. Validate Domino functionality.
9. Delete unneeded AWS resources.
10. Delete the old CloudFormation stack.

### Prerequisites
* terraform version >= 1.5.0
* python >=3.9
* jq
* Bash >= 4
* [hcledit](https://github.com/minamijoyo/hcledit)
* [tfvar](https://github.com/shihanng/tfvar#installation)

### convert.py usage

    usage: convert.py [-h] {create-tfvars,resource-map,set-imports,delete-stack,print-stack} ...

    terraform eks module importer

    options:
      -h, --help            show this help message and exit

    commands:
      {create-tfvars,resource-map,set-imports,delete-stack,print-stack}
	create-tfvars       Generate tfvars
	resource-map        Create resource map for customization/debugging of set-imports command (optional step)
	set-imports         Writes import blocks to the corresponding terraform module
	delete-stack        Get commands to delete old stack
	print-stack         Print CDK stack resources

### Validate requirements
Validate the the requirements are installed and the expected version.

    ./convert.py check-requirements


### Set environment variables
Set `AWS_REGION`, `DEPLOY_ID` and `MOD_VERSION` environment variables with appropriate values.

* `AWS_REGION`  AWS region for the CloudFormation stack.
* `DEPLOY_ID` : Name of the main CloudFormation stack.
* `MOD_VERSION`: Release tag for [terraform-aws-eks](https://github.com/dominodatalab/terraform-aws-eks/releases) in the form `vX.Y.Z` (using `v3.0.0` as an example).

Command:

    export AWS_REGION='us-east-1' DEPLOY_ID='my-main-stack-name' MOD_VERSION='v3.0.0'


### Set Config values
Write environment variables' values to config file.

Command:

     envsubst < config.tpl | tee config.yaml

### Setup the terraform modules.
The following command will create a directory named after variable `$DEPLOY_ID` where it will Initialize the necessary terraform configuration.
It will also copy over `cdk_tf` under the  `$DEPLOY_ID/terraform` directory to centralize the terraform configuration.

Command:

    ./convert.py setup-tf-modules

### Create terraform variables

Running the command below will inspect the existing CDK stack and automatically populate the corresponding Terraform variables for each module. This will generate multiple *.tfvars files: within the `$DEPLOY_ID/terraform` directory:

* `$DEPLOY_ID/terraform/cdk_tf.tfvars`
* `$DEPLOY_ID/terraform/infra.tfvars`
* `$DEPLOY_ID/terraform/cluster.tfvars`
* `$DEPLOY_ID/terraform/nodes.tfvars`

Command:

    ./convert.py create-tfvars --ssh-key-path /path/to/key.pem

* :exclamation: Inspect the generated *tfvars files for correctness.
* :warning: This phase is not the appropriate time for making major changes to the configuration, as the migration to Terraform is still in progress. However, given that the CDK non-managed nodes are not migrated and new managed nodes will be provisioned, you have the flexibility to customize values within the nodes.tfvars file with the exception of availability zones.
* :warning: Note that the ssh key is handled different in the terraform module. With CDK,
we used an existing keypair, while the terraform module creates a keypair for
you. The local key does not need to be the one you used with CDK. The new
autoscaling group nodes and bastion node will be provisioned with the new key.


### Get AWS resources to import

Then, we'll use `convert.py` to generate the Terraform import blocks to import our AWS resources. It will generate a file called `imports.tf` under each of the terraform modules located at:

* `$DEPLOY_ID/terraform/cdk_tf/`
* `$DEPLOY_ID/terraform/infra/`
* `$DEPLOY_ID/terraform/cluster/`
* `$DEPLOY_ID/terraform/nodes/`

Command:

    ./convert.py set-imports


### Review and Configure Node Groups

This conversion process will create a tvfars file with the default nodegroups for the terraform-aws-eks module. The variables file which corresponds to the nodes configuration is located at `$DEPLOY_ID/terraform/nodes.tfvars.json`
Please review the instructions for that module, and configure the nodegroups as desired. Your old nodegroups will remain functional after running the conversion (until the "clean-stack" step).

### Evaluate the Terraform plan

Change into the `DEPLOY_ID` directory:

    cd "$DEPLOY_ID"

Run the `tf.sh` script of the to inspect the plans for `cdk_tf` and `infra`(`cluster` and `nodes` depend on `infra`):

    ./tf.sh cdk_tf plan
    ./tf.sh infra plan

* :exclamation: Please inspect each of the plans as there should be 0 items being destroyed. There will be a lot of output, but near the end you should see output similar to this:

`Plan: 58 to import, 119 to add, 39 to change, 0 to destroy.`

We recommend you inspect the plan carefully for expected imports.

If there is anything Terraform plans to destroy, that is *not* expected and you should carefully scrutinize the output to ensure Terraform isn't doing anything destructive.

Regardless, you should peruse the output to understand what is going to happen. It should be creating new node groups, various security groups and IAM policies, a new bastion, and otherwise leaving things unchanged save for minor tag changes, etc. Major red flags would be large changes or delete/create cycles of the EKS cluster itself, S3 buckets, or EFS.

### Apply the terraform plan for `cdk_tf` and `infra`.

If plans output is reasonable, you can run `apply`:


    ./tf.sh cdk_tf apply
    ./tf.sh infra apply

### Verify `apiservice` health

In order to apply cluster and nodes changes, the cluster must be healthy. In particular, to upgrade Calico `apiservice`s provided by Domino should be double checked:
```
$ kubectl get apiservice -ojsonpath='{range .items[?(@.spec.service.namespace == "domino-platform")]}{.metadata.name} - {.status.conditions[-1].status} ({.status.conditions[-1].reason}){"\n"}{end}'
v1beta1.external.metrics.k8s.io - True (Passed)
v1beta1.metrics.k8s.io - True (Passed)
```

If either are `False`, make sure the corresponding `prometheus-adapter` and `metrics-server` pods are up and running.
If it's not possible get them running, take a backup, delete the `apiservice` objects and then proceed with the infrastructure changes. 

```
kubectl get apiservice v1beta1.external.metrics.k8s.io -oyaml > v1beta1.external.metrics.k8s.io.yml
kubectl delete apiservice v1beta1.external.metrics.k8s.io
```

After the successful conversion, re-apply the object.

```
kubectl create -f v1beta1.external.metrics.k8s.io.yml
```

### Plan and Apply `cluster` and `nodes`.

The `nodes` configuration depends on the `cluster` and `infra` states, Given that `infra` was applied already we need to do the same for cluster.

    ./tf.sh cluster plan

:exclamation: Inspect plan output before running apply. If there is anything Terraform plans to destroy, that is *not* expected and you should carefully scrutinize the output to ensure Terraform isn't doing anything destructive.

    ./tf.sh cluster apply

Once `cluster` has been applied successfully the last module to apply is `nodes`

    ./tf.sh nodes plan

:exclamation: Inspect plan output before running apply. If there is anything Terraform plans to destroy, that is *not* expected and you should carefully scrutinize the output to ensure Terraform isn't doing anything destructive.

    ./tf.sh nodes apply


Once Terraform is finished, the most critical work is done.

### Scale down the old autoscaling groups

You will have two sets of autoscaling groups at this point, so you will want to scale down the old ones.

Set min/max/desired to 0 on all CDK-provisioned auto-scaling groups.

The *old* ones look like this:

    clustername-platform-0-us-east-1

The *new* ones look like this:

    eks-clustername-platform-0-abcd1234-abcd-1234-5678-abcd12345678

Once all the Domino pods are live on the *new* nodes, Domino should be back up and functional.

### Delete unneeded AWS resources

There are various resources CDK managed, but terraform does not need, such as:

* The *old* autoscaling groups
* The *old* bastion and bastion EIP
* Various CDK lambdas and associated state machines
* Any network interfaces associated
* The `clustername-sharedNodeSG` security group
* The `clustername-endpoints` security group

There is a `clean-stack` command to help clean these up.

    ./convert.py clean-stack

You'll note that there is a comment about security groups:

    {'Security groups to be deleted': ['sg-06d2154938a2e4a07',
                                       'sg-03d806e3b0d455776']}

    However, some security groups have rules referencing them that must be removed:

    {'sg-06d2154938a2e4a07 is referenced by': {'sg-04396807b014ed3d5',
                                               'sg-0461c2c89e69acd81',
                                               'sg-06d2154938a2e4a07'}}

These rules aren't cleaned up automatically by default, as they can involve editing security groups outside the scope of the CloudFormation. You can choose to clean them up manually, or run with the `--remove-security-group-references` argument.

By default, this command does *not* actually make changes. To run the clean process for real, add `--delete`:

    ./convert.py clean-stack --delete [--remove-security-group-references]

### Delete the old cloudformation stack

Enter the `cloudformation-only/` subdirectory, and provision that terraform:

    cat <<EOF >> terraform.tfvars
    region="us-east-1"
    tags={}
    EOF
    terraform init
    terraform plan -out=terraform.plan
    terraform apply terraform.plan

This will provision an IAM role that *only has permission to CloudFormation and _nothing else_*.

Once this is provisioned, run `convert.py`'s `delete-stack` command and read its instructions:

    ./convert.py delete-stack

    Manual instructions:
    First run this delete-stack command using the cloudformation-only role:

    aws cloudformation delete-stack --role arn:aws:iam::1234567890:role/cloudformation-only

    This will *attempt* to delete the entire CDK stack, but *intentionally fail* so as to leave the stack in the delete failed state, with all resources having failed. This opens the gate to retain every resource, so the following runs can delete the stack(s) and only the stack(s). After running the first command, rerun this and then execute the following to safely delete the stacks:

    <various delete-stack commands for each stack, with the --retain-resources argument propagated>

    To perform this process automatically, add the --delete argument

Rerun the `delete-stack` command with `--delete` (or run the boto commands manually, if you prefer):

    ./convert.py delete-stack --delete

This may seem a bit strange, but there is no direct way to only remove a CloudFormation stack, while retaining all the resources. However, once a CloudFormation stack deletion even has failed, it is possible to re-attempt this stack deletion and specify failed resources to retain. So what this process does is use the limited permission role to cause all resource deletions to fail, and then specifies all extant resources as resources to retain on the subsequent attempt.

The reason the `convert.py delete-stack` must be rerun is the resources to retain need to be re-evaluated after the intial attempt, as a few CloudFormation-level resources *will* get successfully deleted (and that is normal).
